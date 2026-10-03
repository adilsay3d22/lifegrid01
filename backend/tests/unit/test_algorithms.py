"""Phase 4/5 algorithm tests: FR-FC-02/03 and the Phase 4 exit; FR-RD-02/03/06; optimizer >= fallback (section 17)."""

import numpy as np
import pytest
from ortools.linear_solver import pywraplp

from app.core.enums import Abo, Component, Rh
from app.modules.compatibility.rules import seed_rows
from app.modules.forecasting import engine
from app.modules.redistribution import optimizer as O
from simulation.generator import generate
from simulation.scenario import load

RANKS = {(ra, rr, da, dr): k for c, ra, rr, da, dr, k in seed_rows() if c is Component.red_cells}
OP, ON = (Abo.O, Rh.pos), (Abo.O, Rh.neg)


def test_fr_fc_02_seven_rows_with_ordered_band():
    y = np.random.default_rng(3).poisson(4, 120)
    r = engine.forecast(y, 7)
    assert len(r.point) == 7 and (r.low <= r.point).all() and (r.point <= r.high).all() and (r.low >= 0).all()


def test_fr_fc_02_band_holds_for_tiny_sparse_rate():
    y = np.zeros(100)
    y[[40, 90]] = 1
    r = engine.forecast(y, 7)
    assert r.model in {"poisson", "seasonal_naive"} and (r.low <= r.point).all() and (r.point <= r.high).all()


def test_fr_fc_03_model_and_error_reported():
    r = engine.forecast(np.random.default_rng(1).poisson(6, 150), 7)
    assert r.model in engine.MODELS and r.backtest_mae <= r.baseline_mae


def test_phase4_exit_chosen_models_beat_seasonal_baseline_on_normal_scenario():
    """Fit on 150 days of the `normal` scenario, score the next 28 days out of sample for every hospital series."""
    w = generate(load("normal"), 7)
    chosen, naive = [], []
    for y in list(w.demand.values())[:60]:
        for origin in (150, 157, 164, 171):
            f = engine.forecast(y[:origin], 7)
            chosen.append(np.abs(f.point - y[origin:origin + 7]).mean())
            naive.append(np.abs(engine.seasonal_naive(y[:origin], 7).point - y[origin:origin + 7]).mean())
    assert np.mean(chosen) < np.mean(naive)


def _inp(stock, demand, **kw):  # type: ignore[no-untyped-def]
    sites = ["BANK", "H1", "H2"]
    dist = {(a, b): 0.0 if a == b else 10.0 for a in sites for b in sites}
    return O.PlanInput(sites, dist, stock, demand, RANKS, horizon=3, min_life_days=kw.pop("min_life", 5), **kw)


def test_fr_rd_02_and_03_moves_have_fields_and_enough_shelf_life():
    stock = {("BANK", *OP, 5): 30, ("BANK", *OP, 2): 10, ("H2", *ON, 1): 4}  # bucket 2 and 1 are below min life 5
    demand = {("H1", *OP, t): 5 for t in range(3)} | {("H1", *ON, t): 1 for t in range(3)}
    out = O.optimize(_inp(stock, demand))
    assert out.status == "OPTIMAL" and out.moves
    for m in out.moves:
        assert m.units > 0 and m.from_site != m.to_site and m.bucket >= 5
    assert out.with_plan.short < out.without.short


def test_optimizer_respects_lane_limits():
    stock = {("BANK", *OP, 5): 100}
    sites = ["BANK"] + [f"H{i}" for i in range(6)]
    dist = {(a, b): 0.0 if a == b else 10.0 for a in sites for b in sites}
    demand = {(f"H{i}", *OP, t): 3 for i in range(6) for t in range(3)}
    out = O.optimize(O.PlanInput(sites, dist, stock, demand, RANKS, max_lanes=3, lane_capacity=40))
    lanes = {(m.from_site, m.to_site) for m in out.moves}
    assert len([lane for lane in lanes if lane[0] == "BANK"]) <= 3
    per_lane = {}
    for m in out.moves:
        per_lane[(m.from_site, m.to_site)] = per_lane.get((m.from_site, m.to_site), 0) + m.units
    assert max(per_lane.values()) <= 40


def test_fr_rd_06_forced_timeout_returns_fallback_plan(monkeypatch):
    real = pywraplp.Solver.Solve

    def slow(self, *a):  # type: ignore[no-untyped-def]
        return pywraplp.Solver.NOT_SOLVED if any(v.integer() for v in self.variables()) else real(self, *a)

    monkeypatch.setattr(pywraplp.Solver, "Solve", slow)
    out = O.optimize(_inp({("BANK", *OP, 5): 20}, {("H1", *OP, t): 5 for t in range(3)}), time_limit_s=0.1)
    assert out.is_fallback and out.status == "TIME_LIMIT" and out.moves


CASES = [
    ({("BANK", *OP, 5): 20, ("H1", *OP, 1): 6}, {("H1", *OP, t): 4 for t in range(3)} | {("H2", *OP, t): 3 for t in range(3)}),
    ({("H1", *OP, 1): 8, ("H2", *ON, 6): 6}, {("H2", *OP, t): 3 for t in range(3)} | {("H1", *ON, t): 1 for t in range(3)}),
    ({("BANK", *ON, 9): 9, ("BANK", *OP, 9): 3}, {("H1", *OP, t): 2 for t in range(3)} | {("H2", *ON, t): 2 for t in range(3)}),
]


def _cost(inp: O.PlanInput, ev: O.Evaluation) -> float:
    w = inp.weights
    return w["expired"] * ev.expired + sum(w["unmet"] * (w["rh_neg_unmet_multiplier"] if r is Rh.neg else 1) * v for (_, _, r), v in ev.short_by.items())


@pytest.mark.parametrize("stock,demand", CASES)
def test_optimizer_beats_or_equals_fallback(stock, demand):
    inp = _inp(stock, demand, min_life=1)
    opt = O.optimize(inp)
    fb = O.evaluate(O.replace(inp, demand=O.integer_demand(inp.demand, 3)), O.fallback(inp))
    assert _cost(inp, opt.with_plan) <= _cost(inp, fb) + 1e-6


def test_integer_demand_keeps_totals():
    d = {("H1", *OP, t): 0.37 for t in range(3)} | {("H2", *ON, t): 2.6 for t in range(3)}
    out = O.integer_demand(d, 3)
    assert sum(v for k, v in out.items() if k[0] == "H1") == 1 and sum(v for k, v in out.items() if k[0] == "H2") == 8
    assert all(float(v).is_integer() for v in out.values())

"""Phase 3: FR-SIM-01 (deterministic generation), NFR-15 (identical runs), FR-SIM-02 (policies on one scenario)."""

import json

import numpy as np

from simulation import runner
from simulation.engine import run
from simulation.generator import generate
from simulation.scenario import load


def _short():  # type: ignore[no-untyped-def]
    sc = load("normal")
    return sc.model_copy(update={"days": 66, "warmup_days": 56})


def test_fr_sim_01_same_seed_same_world_different_seed_differs():
    a, b, c = generate(load("normal"), 5), generate(load("normal"), 5), generate(load("normal"), 6)
    assert [s.__dict__ for s in a.sites] == [s.__dict__ for s in b.sites]
    assert all(np.array_equal(a.demand[k], b.demand[k]) for k in a.demand)
    assert a.requests == b.requests and a.donors == b.donors
    assert any(not np.array_equal(a.demand[k], c.demand[k]) for k in a.demand)


def test_nfr_15_same_seed_same_metrics_byte_for_byte():
    sc = _short()
    for policy in "ABC":
        r1 = json.dumps(run(generate(sc, 11), policy).metrics, sort_keys=True)
        r2 = json.dumps(run(generate(sc, 11), policy).metrics, sort_keys=True)
        assert r1 == r2


def test_all_scenarios_load():
    for name in ("normal", "donation_drop", "trauma_spike", "transport_disruption", "bad_forecast", "large_region"):
        assert load(name).name == name
    assert len(generate(load("large_region"), 1).sites) == 100


def test_fr_sim_02_policies_run_and_write_results(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    monkeypatch.setattr(runner, "load", lambda name: _short())
    rows = runner.experiment(["normal"], ["A", "B", "C"], seeds=1, workers=1)
    assert {r["policy"] for r in rows} == {"A", "B", "C"}
    assert len(list((tmp_path / "runs").glob("*.json"))) == 3
    report = runner.report().read_text()
    assert "| expired_units |" in report and (tmp_path / "results.csv").exists()

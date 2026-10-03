"""Redistribution optimizer and rule-based fallback as pure functions (spec section 13.2).

One problem per component. Inputs are plain dicts so the API, workers and simulator share this code.
Decision variables: x (units moved today, integer), z (lane used, binary); y/w/u (use, waste, unmet) are continuous —
they are an allocation of fixed integer stock, so the LP relaxation is tight enough for planning (decision 0003).
"""

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field, replace

from ortools.linear_solver import pywraplp

from app.core.enums import Abo, Rh

Group = tuple[Abo, Rh]
StockKey = tuple[str, Abo, Rh, int]  # site, donor group, expiry bucket e (days left; e == horizon means "beyond")
DemandKey = tuple[str, Abo, Rh, int]  # site, recipient group, day t


@dataclass
class PlanInput:
    sites: list[str]
    dist_km: dict[tuple[str, str], float]
    stock: dict[StockKey, int]
    demand: dict[DemandKey, float]
    ranks: dict[tuple[Abo, Rh, Abo, Rh], int]  # (recipient abo, rh, donor abo, rh) -> rank; absent = incompatible
    horizon: int = 3
    min_life_days: int = 5
    weights: dict[str, float] = field(default_factory=lambda: {"expired": 1.0, "unmet": 10.0, "rh_neg_unmet_multiplier": 3.0,
                                                               "unit_km": 0.01, "rank_step": 0.1, "lane": 0.5})
    lane_capacity: int = 40
    max_lanes: int = 3
    max_neighbours: int = 12  # candidate lanes per site; keeps 100-site regions tractable (NFR-08)
    lane_factor: float = 1.0  # < 1 models a transport disruption


@dataclass
class Move:
    from_site: str
    to_site: str
    abo: Abo
    rh: Rh
    bucket: int
    units: int


@dataclass
class Evaluation:
    expired: float
    short: float
    short_by: dict[tuple[str, Abo, Rh], float]
    expired_by: dict[tuple[str, Abo, Rh], float]


@dataclass
class PlanOutput:
    moves: list[Move]
    status: str
    seconds: float
    is_fallback: bool
    without: Evaluation
    with_plan: Evaluation


def bucket(days_left: int, horizon: int, min_life: int) -> int:
    """Expiry bucket e (spec 13.2). Each day inside the horizon is its own bucket; beyond it units only differ in
    whether they may travel, so they share bucket `horizon` (cannot travel yet) or `max(horizon, min_life)` (can)."""
    if days_left < horizon:
        return days_left
    return max(horizon, min_life) if days_left >= min_life else horizon


def integer_demand(demand: dict[DemandKey, float], horizon: int) -> dict[DemandKey, float]:
    """Whole-unit daily demand that keeps each series' running total: round the cumulative sum, then difference.
    Fractional demand (0.37/day) lets the LP spread slivers of one unit across sites, which makes the bound weak
    and the MIP slow; integral demand restores a near-transportation structure (decision 0003)."""
    out: dict[DemandKey, float] = {}
    series = {(s_, a, r) for (s_, a, r, _) in demand}
    for s_, a, r in series:
        cum, prev = 0.0, 0
        for t in range(horizon):
            cum += demand.get((s_, a, r, t), 0.0)
            now_ = int(math.floor(cum + 0.5))
            if now_ > prev:
                out[(s_, a, r, t)] = float(now_ - prev)
            prev = now_
    return out


def _unmet_weight(inp: PlanInput, rh: Rh) -> float:
    w = inp.weights
    return w["unmet"] * (w["rh_neg_unmet_multiplier"] if rh is Rh.neg else 1.0)


def _neighbours(inp: PlanInput) -> dict[str, list[str]]:
    out = {}
    for i in inp.sites:
        others = sorted((j for j in inp.sites if j != i), key=lambda j: inp.dist_km[(i, j)])
        out[i] = others[: inp.max_neighbours]
    return out


def _model(inp: PlanInput, stock: dict[StockKey, int], allow_moves: bool, time_limit_s: float, x_integer: bool = True):  # type: ignore[no-untyped-def]
    """Build the section 13.2 model. Returns (solver, x, w, u) so callers can read values."""
    H = inp.horizon
    w8 = inp.weights
    s = pywraplp.Solver.CreateSolver("SCIP" if allow_moves else "GLOP")
    s.SetTimeLimit(int(time_limit_s * 1000))
    inf = s.infinity()

    x: dict[tuple[str, str, Abo, Rh, int], pywraplp.Variable] = {}
    z: dict[tuple[str, str], pywraplp.Variable] = {}
    on_lane: dict[tuple[str, str], list[pywraplp.Variable]] = defaultdict(list)
    arrivals: dict[tuple[str, Abo, Rh, int], list[pywraplp.Variable]] = defaultdict(list)
    departures: dict[tuple[str, Abo, Rh, int], list[pywraplp.Variable]] = defaultdict(list)
    if allow_moves:
        nb = _neighbours(inp)
        cap = max(0, int(inp.lane_capacity * inp.lane_factor))
        for (i, a, r, e), n in stock.items():
            if n <= 0 or e < inp.min_life_days or cap == 0:
                continue
            for j in nb[i]:
                v = s.IntVar(0, n, "") if x_integer else s.NumVar(0, n, "")
                x[(i, j, a, r, e)] = v
                departures[(i, a, r, e)].append(v)
                arrivals[(j, a, r, e)].append(v)
                on_lane[(i, j)].append(v)
        for (i, j), vs in on_lane.items():
            z[(i, j)] = s.BoolVar("")
            s.Add(sum(vs) <= cap * z[(i, j)])
            for v in vs:  # per-variable link: same feasible set, much tighter LP bound (solves ~10x faster)
                s.Add(v <= min(cap, int(v.ub())) * z[(i, j)])
        lanes_out: dict[str, list[pywraplp.Variable]] = defaultdict(list)
        for (i, _), zv in z.items():
            lanes_out[i].append(zv)
        for zs in lanes_out.values():
            s.Add(sum(zs) <= inp.max_lanes)
        for k, vs in departures.items():
            s.Add(sum(vs) <= stock[k])

    # Usage y(s, g, h, e, t) for every site/bucket that can hold stock after moves.
    holders = {k for k, n in stock.items() if n > 0} | set(arrivals)
    use_of: dict[tuple[str, Abo, Rh, int], list[pywraplp.Variable]] = defaultdict(list)  # by holder
    serve: dict[DemandKey, list[pywraplp.Variable]] = defaultdict(list)
    obj = []
    recipients_of: dict[Group, list[tuple[Abo, Rh, int]]] = defaultdict(list)
    for (ha, hr, da, dr), rank in inp.ranks.items():
        recipients_of[(da, dr)].append((ha, hr, rank))
    for (site, ga, gr, e) in holders:
        for t in range(min(e, H - 1) + 1):
            for ha, hr, rank in recipients_of[(ga, gr)]:
                if inp.demand.get((site, ha, hr, t), 0) <= 0:
                    continue
                v = s.NumVar(0, inf, "")
                use_of[(site, ga, gr, e)].append(v)
                serve[(site, ha, hr, t)].append(v)
                obj.append(w8["rank_step"] * (rank - 1) * v)
    w: dict[tuple[str, Abo, Rh, int], pywraplp.Variable] = {}
    for key in holders:
        site, ga, gr, e = key
        level = stock.get(key, 0) - sum(departures.get(key, [])) + sum(arrivals.get(key, []))
        used = sum(use_of.get(key, []))
        if e < H:
            w[key] = s.NumVar(0, inf, "")
            s.Add(used + w[key] == level)
            obj.append(w8["expired"] * w[key])
        else:
            s.Add(used <= level)
    u: dict[DemandKey, pywraplp.Variable] = {}
    for key, d in inp.demand.items():
        if d <= 0:
            continue
        u[key] = s.NumVar(0, inf, "")
        s.Add(sum(serve.get(key, [])) + u[key] == d)
        obj.append(_unmet_weight(inp, key[2]) * u[key])
    obj += [w8["unit_km"] * inp.dist_km[(i, j)] * v for (i, j, *_), v in x.items()]
    obj += [w8["lane"] * zv for zv in z.values()]
    s.Minimize(sum(obj))
    return s, x, w, u


def evaluate(inp: PlanInput, moves: list[Move]) -> Evaluation:
    """Projected expired and unmet units if `moves` happen today and stock is then used optimally (FR-RD-07)."""
    stock = dict(inp.stock)
    for m in moves:
        stock[(m.from_site, m.abo, m.rh, m.bucket)] = stock.get((m.from_site, m.abo, m.rh, m.bucket), 0) - m.units
        stock[(m.to_site, m.abo, m.rh, m.bucket)] = stock.get((m.to_site, m.abo, m.rh, m.bucket), 0) + m.units
    s, _, w, u = _model(inp, stock, allow_moves=False, time_limit_s=30)
    s.Solve()
    short_by: dict[tuple[str, Abo, Rh], float] = defaultdict(float)
    expired_by: dict[tuple[str, Abo, Rh], float] = defaultdict(float)
    for (site, a, r, _), v in u.items():
        short_by[(site, a, r)] += v.solution_value()
    for (site, a, r, _), v in w.items():
        expired_by[(site, a, r)] += v.solution_value()
    return Evaluation(round(sum(expired_by.values()), 3), round(sum(short_by.values()), 3), dict(short_by), dict(expired_by))


_EMPTY = Evaluation(0, 0, {}, {})


def optimize(inp: PlanInput, time_limit_s: float = 30, project: bool = True) -> PlanOutput:
    """Solve; on timeout or failure, fall back to the rule-based plan (FR-RD-06). `project=False` skips the
    with/without projections (the simulator measures outcomes directly)."""
    t0 = time.perf_counter()
    inp = replace(inp, demand=integer_demand(inp.demand, inp.horizon))
    without = evaluate(inp, []) if project else _EMPTY
    params = pywraplp.MPSolverParameters()
    # Near-exact: a looser gap admits useless moves (transport cost is tiny next to shortage penalties).
    params.SetDoubleParam(params.RELATIVE_MIP_GAP, 1e-4)
    # Exact shortcut: with integral stock and demand the optimum usually has integral x even when x is continuous;
    # if so it is optimal for the integer model too. Otherwise re-solve with integer x in the remaining time.
    s, x, _, _ = _model(inp, inp.stock, allow_moves=True, time_limit_s=time_limit_s, x_integer=False)
    status = s.Solve(params)
    if status == pywraplp.Solver.OPTIMAL and any(abs(v.solution_value() - round(v.solution_value())) > 1e-6 for v in x.values()):
        left = max(1.0, time_limit_s - (time.perf_counter() - t0))
        s, x, _, _ = _model(inp, inp.stock, allow_moves=True, time_limit_s=left, x_integer=True)
        status = s.Solve(params)
    seconds = time.perf_counter() - t0
    if status != pywraplp.Solver.OPTIMAL:
        name = {pywraplp.Solver.FEASIBLE: "TIME_LIMIT", pywraplp.Solver.NOT_SOLVED: "TIME_LIMIT"}.get(status, "FAILED")
        moves = fallback(inp)
        return PlanOutput(moves, name, round(time.perf_counter() - t0, 3), True, without, evaluate(inp, moves) if project else _EMPTY)
    moves = [Move(i, j, a, r, e, round(v.solution_value())) for (i, j, a, r, e), v in x.items() if round(v.solution_value()) > 0]
    return PlanOutput(moves, "OPTIMAL", round(seconds, 3), False, without, evaluate(inp, moves) if project else _EMPTY)


def fallback(inp: PlanInput) -> list[Move]:
    """Rule-based plan, also simulator policy B. Per site, use own stock first (rank, then FEFO); leftovers are surplus,
    shortfalls are deficits. Match surplus to the nearest compatible deficit, largest benefit first."""
    H = inp.horizon
    inp = replace(inp, demand=integer_demand(inp.demand, H))
    left: dict[StockKey, int] = {k: n for k, n in inp.stock.items() if n > 0}
    donors: dict[Group, list[Group]] = defaultdict(list)
    for (ha, hr, da, dr), _ in sorted(inp.ranks.items(), key=lambda kv: kv[1]):
        donors[(ha, hr)].append((da, dr))
    deficit: dict[tuple[str, Abo, Rh], float] = defaultdict(float)
    for (site, ha, hr, t), d in sorted(inp.demand.items(), key=lambda kv: kv[0][3]):  # day by day
        need = int(d)
        for da, dr in donors[(ha, hr)]:
            for e in sorted(e for (s_, a, r, e) in left if s_ == site and (a, r) == (da, dr) and e >= t):
                take = min(left[(site, da, dr, e)], need)
                left[(site, da, dr, e)] -= take
                need -= take
            if need <= 0:
                break
        deficit[(site, ha, hr)] += max(need, 0)
    cands = []
    for (dsite, ha, hr), amount in deficit.items():
        if amount < 0.5:
            continue
        for (ssite, da, dr, e), n in left.items():
            rank = inp.ranks.get((ha, hr, da, dr))
            if n <= 0 or ssite == dsite or rank is None or e < inp.min_life_days:
                continue
            d = inp.dist_km[(ssite, dsite)]
            benefit = _unmet_weight(inp, hr) + (inp.weights["expired"] if e < H else 0) \
                - inp.weights["unit_km"] * d - inp.weights["rank_step"] * (rank - 1)
            cands.append((-benefit, d, e, ssite, dsite, da, dr, ha, hr))
    cands.sort()
    want = {k: math.floor(v + 0.5) for k, v in deficit.items()}
    lanes: dict[str, set[str]] = defaultdict(set)
    lane_load: dict[tuple[str, str], int] = defaultdict(int)
    cap = int(inp.lane_capacity * inp.lane_factor)
    moves: dict[tuple[str, str, Abo, Rh, int], int] = defaultdict(int)
    for _, _, e, ssite, dsite, da, dr, ha, hr in cands:
        k_need, k_src = (dsite, ha, hr), (ssite, da, dr, e)
        if want.get(k_need, 0) <= 0 or left[k_src] <= 0:
            continue
        if dsite not in lanes[ssite] and len(lanes[ssite]) >= inp.max_lanes:
            continue
        qty = min(want[k_need], left[k_src], cap - lane_load[(ssite, dsite)])
        if qty <= 0:
            continue
        lanes[ssite].add(dsite)
        lane_load[(ssite, dsite)] += qty
        left[k_src] -= qty
        want[k_need] -= qty
        moves[(ssite, dsite, da, dr, e)] += qty
    return [Move(i, j, a, r, e, n) for (i, j, a, r, e), n in moves.items() if n > 0]

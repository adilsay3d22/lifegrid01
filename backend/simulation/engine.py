"""Fast-mode simulator (spec section 14): steps day by day through a generated world under a policy.

Supply model: collections arrive at blood banks on delivery days; hospitals reorder up to a fixed level from the
nearest bank (all policies). Policy A adds nothing; B adds the rule-based lateral sharing; C adds forecasts and the
optimizer. All policies behave like A during warm-up so they start from the same state. Never reads the wall clock
except to time the solver (reported separately from metrics).
"""

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from app.core.enums import GROUPS, Abo, Component, Rh
from app.modules.compatibility.rules import seed_rows
from app.modules.forecasting import engine as fc
from app.modules.redistribution.optimizer import Move, PlanInput, bucket, fallback, optimize
from simulation.generator import World, group_mix, recipient_groups

SHELF = {Component.red_cells: 42, Component.platelets: 5, Component.plasma: 365}
MIN_LIFE = {Component.red_cells: 5, Component.platelets: 1, Component.plasma: 30}
COVER_DAYS = {Component.red_cells: 7, Component.platelets: 3, Component.plasma: 14}  # hospital reorder level
AGE_AT_ARRIVAL = {Component.red_cells: (1, 8), Component.platelets: (1, 2), Component.plasma: (5, 40)}
SUPPLY_FACTOR = 1.08  # collections run slightly above expected demand
HORIZON = 3
K_UPPER = 0.5  # D = point + k (high - point)

RANKS: dict[Component, dict[tuple[Abo, Rh, Abo, Rh], int]] = defaultdict(dict)
for _c, _ra, _rr, _da, _dr, _k in seed_rows():
    RANKS[_c][(_ra, _rr, _da, _dr)] = _k
DONORS: dict[tuple[Component, Abo, Rh], list[tuple[Abo, Rh]]] = defaultdict(list)
for _c, _r in RANKS.items():
    for (_ra, _rr, _da, _dr), _k in sorted(_r.items(), key=lambda kv: kv[1]):
        DONORS[(_c, _ra, _rr)].append((_da, _dr))


def donor_groups(c: Component) -> list[tuple[Abo, Rh]]:
    return [(a, Rh.pos) for a in Abo] if c is Component.plasma else list(GROUPS)


@dataclass
class Lot:
    expiry: int  # last usable day
    collected: int
    n: int


class Stock:
    def __init__(self) -> None:
        self.lots: dict[tuple[str, Component, Abo, Rh], list[Lot]] = defaultdict(list)

    def add(self, site: str, c: Component, g: tuple[Abo, Rh], expiry: int, collected: int, n: int) -> None:
        if n > 0:
            lots = self.lots[(site, c, *g)]
            lots.append(Lot(expiry, collected, n))
            lots.sort(key=lambda lot: lot.expiry)

    def on_hand(self, site: str, c: Component, g: tuple[Abo, Rh], day: int, min_expiry: int | None = None) -> int:
        lo = day if min_expiry is None else min_expiry
        return sum(lot.n for lot in self.lots.get((site, c, *g), []) if lot.expiry >= lo)

    def take(self, site: str, c: Component, g: tuple[Abo, Rh], n: int, min_expiry: int, exact_expiry: int | None = None) -> list[Lot]:
        """Remove up to n units first-expired-first-out (optionally only from one expiry day)."""
        out: list[Lot] = []
        for lot in self.lots.get((site, c, *g), []):
            if n <= 0:
                break
            if lot.expiry < min_expiry or (exact_expiry is not None and lot.expiry != exact_expiry):
                continue
            k = min(n, lot.n)
            lot.n -= k
            n -= k
            out.append(Lot(lot.expiry, lot.collected, k))
        if out:
            self.lots[(site, c, *g)] = [lot for lot in self.lots[(site, c, *g)] if lot.n > 0]
        return out


@dataclass
class Metrics:
    issued: int = 0
    expired: int = 0
    unmet: int = 0
    shortage_events: int = 0
    unmet_rh_neg: int = 0
    shortage_events_rh_neg: int = 0
    age_at_issue_sum: int = 0
    transfers: int = 0
    transfer_units: int = 0
    unit_km: float = 0.0
    lanes_used: int = 0
    fallbacks: int = 0
    solver_runs: int = 0
    expired_by_component: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    unmet_by_component: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def summary(self) -> dict[str, float]:
        total = self.issued + self.expired
        return {
            "expired_units": self.expired, "expired_share": round(self.expired / total, 5) if total else 0.0,
            "shortage_events": self.shortage_events, "unmet_units": self.unmet,
            "shortage_events_rh_neg": self.shortage_events_rh_neg, "unmet_units_rh_neg": self.unmet_rh_neg,
            "avg_age_at_issue_days": round(self.age_at_issue_sum / self.issued, 3) if self.issued else 0.0,
            "issued_units": self.issued, "transfers": self.transfers, "transfer_units": self.transfer_units,
            "unit_km": round(self.unit_km, 1), "lanes_used": self.lanes_used, "fallback_count": self.fallbacks,
            **{f"expired_{k}": v for k, v in sorted(self.expired_by_component.items())},
            **{f"unmet_{k}": v for k, v in sorted(self.unmet_by_component.items())},
        }


@dataclass
class RunResult:
    metrics: dict[str, float]
    timing: dict[str, float]  # wall-clock, excluded from reproducibility checks
    stock: Stock
    usage: dict[tuple[str, Component, Abo, Rh], np.ndarray]


class Simulation:
    def __init__(self, world: World, policy: str, stop_day: int | None = None, demand_k: float = K_UPPER) -> None:
        if policy not in ("A", "B", "C"):
            raise ValueError("policy D (donor matching) arrives with phase 6")
        self.w, self.policy, self.sc, self.k = world, policy, world.scenario, demand_k
        self.days = stop_day if stop_day is not None else self.sc.days
        self.stock = Stock()
        self.usage = {k: np.zeros(self.sc.days, dtype=np.int32) for k in world.demand}
        self.m = Metrics()
        self.rng = np.random.default_rng([world.seed, 1])  # collections: identical across policies
        self.noise_rng = np.random.default_rng([world.seed, 2])
        self.mix = group_mix(self.sc)
        self.solver_seconds = 0.0
        self._fc: dict[tuple[str, Component, Abo, Rh], tuple[int, np.ndarray]] = {}
        self.bank_of = {h.code: sorted(world.banks, key=lambda b: world.dist[(h.code, b.code)]) for h in world.hospitals}
        n = self.sc.supply.deliveries_per_week
        weekdays = sorted({int(i * 7 / n) for i in range(n)})
        # days until the next delivery, per delivery weekday (sizes each collection)
        self.gap = {wd: (weekdays[(k + 1) % len(weekdays)] - wd) % 7 or 7 for k, wd in enumerate(weekdays)}
        self.levels = {(h.code, c, *g): math.ceil(world.rate.get((h.code, c, *g), 0.0) * COVER_DAYS[c])
                       for h in world.hospitals for c in Component for g in donor_groups(c)}
        self.net_rate = {(c, g): sum(world.rate.get((h.code, c, *g), 0.0) for h in world.hospitals)
                         for c in Component for g in donor_groups(c)}
        self._prefill()

    # --- disruptions -------------------------------------------------------------------------------------------
    def _factor(self, kind: str, d: int) -> float:
        f = 1.0
        for dis in self.sc.disruptions:
            if dis.type == kind and dis.start <= d < dis.start + dis.days:
                f *= dis.factor
        return f

    # --- supply -------------------------------------------------------------------------------------------------
    def _level(self, site: str, c: Component, g: tuple[Abo, Rh]) -> int:
        return self.levels[(site, c, *g)]

    def _prefill(self) -> None:
        """Start with hospitals at their reorder level and banks holding a week of network demand."""
        for c in Component:
            lo, hi = AGE_AT_ARRIVAL[c]
            for h in self.w.hospitals:
                for g in donor_groups(c):
                    n = self._level(h.code, c, g)
                    for _ in range(n):  # spread ages so expiries are staggered
                        age = int(self.rng.integers(lo, SHELF[c]))
                        self.stock.add(h.code, c, g, SHELF[c] - age, -age, 1)
            for b in self.w.banks:
                for g in donor_groups(c):
                    n = math.ceil(self._network_rate(c, g) * 7 / len(self.w.banks))
                    for _ in range(n):
                        age = int(self.rng.integers(lo, SHELF[c]))
                        self.stock.add(b.code, c, g, SHELF[c] - age, -age, 1)

    def _network_rate(self, c: Component, g: tuple[Abo, Rh]) -> float:
        return self.net_rate[(c, g)]

    def _collect(self, d: int) -> None:
        fill = self.sc.supply.fill_rate * self._factor("donation_drop", d)
        for c in Component:
            lo, hi = AGE_AT_ARRIVAL[c]
            for g in donor_groups(c):
                lam = self._network_rate(c, g) * self.gap[d % 7] * SUPPLY_FACTOR * fill
                n = int(self.rng.poisson(lam))
                split = self.rng.multinomial(n, [1 / len(self.w.banks)] * len(self.w.banks))
                age = int(self.rng.integers(lo, hi + 1))
                for b, k in zip(self.w.banks, split, strict=True):
                    self.stock.add(b.code, c, g, d + SHELF[c] - age, d - age, int(k))

    def _orders(self, d: int) -> None:
        transport = self._factor("transport_disruption", d)
        for h in self.w.hospitals:
            for c in Component:
                for g in donor_groups(c):
                    need = int((self._level(h.code, c, g) - self.stock.on_hand(h.code, c, g, d)) * transport)
                    for b in self.bank_of[h.code]:
                        if need <= 0:
                            break
                        for lot in self.stock.take(b.code, c, g, need, d + MIN_LIFE[c]):
                            self.stock.add(h.code, c, g, lot.expiry, lot.collected, lot.n)
                            need -= lot.n

    # --- policies -----------------------------------------------------------------------------------------------
    def _demand_view(self, d: int, c: Component) -> dict[tuple[str, Abo, Rh, int], float]:
        out: dict[tuple[str, Abo, Rh, int], float] = {}
        for h in self.w.hospitals:
            for g in recipient_groups(c):
                key = (h.code, c, *g)
                hist = self.usage[key][:d]
                if self.policy == "B":  # rule-based: recent average per day
                    pts = np.full(HORIZON, hist[-28:].mean() if hist.size else 0.0)
                else:
                    f0, arr = self._fc.get(key, (-99, np.array([])))
                    if d - f0 >= 7 or arr.size == 0:
                        r = fc.forecast(hist, h=7 + HORIZON, allowed=["seasonal_naive", "poisson", "ets_fast"])
                        arr = r.point + self.k * (r.high - r.point)
                        if self.sc.forecast_noise:
                            arr = arr * np.exp(self.noise_rng.normal(0, self.sc.forecast_noise, arr.size))
                        self._fc[key] = (d, arr)
                        f0 = d
                    pts = arr[d - f0: d - f0 + HORIZON]
                for t, v in enumerate(pts):
                    if v > 0:
                        out[(h.code, *g, t)] = float(v)
        return out

    def _transfers(self, d: int) -> None:
        lane_factor = self._factor("transport_disruption", d)
        lanes: set[tuple[str, str]] = set()
        for c in Component:
            cap_e = max(HORIZON, MIN_LIFE[c])
            stock: dict[tuple[str, Abo, Rh, int], int] = defaultdict(int)
            for (site, cc, a, r), lots in self.stock.lots.items():
                if cc is c:
                    for lot in lots:
                        if lot.expiry >= d:
                            stock[(site, a, r, bucket(lot.expiry - d, HORIZON, MIN_LIFE[c]))] += lot.n
            inp = PlanInput([s.code for s in self.w.sites], self.w.dist, dict(stock), self._demand_view(d, c), RANKS[c],
                            horizon=HORIZON, min_life_days=MIN_LIFE[c], lane_factor=lane_factor)
            if self.policy == "B":
                moves = fallback(inp)
            else:
                t0 = time.perf_counter()
                out = optimize(inp, time_limit_s=30, project=False)
                self.solver_seconds += time.perf_counter() - t0
                self.m.solver_runs += 1
                self.m.fallbacks += out.is_fallback
                moves = out.moves
            for mv in moves:
                self._apply(d, c, mv, cap_e)
                lanes.add((mv.from_site, mv.to_site))
        self.m.lanes_used += len(lanes)

    def _apply(self, d: int, c: Component, mv: Move, cap_e: int) -> None:
        exact = None if mv.bucket >= cap_e else d + mv.bucket
        moved = 0
        for lot in self.stock.take(mv.from_site, c, (mv.abo, mv.rh), mv.units, d + mv.bucket, exact):
            self.stock.add(mv.to_site, c, (mv.abo, mv.rh), lot.expiry, lot.collected, lot.n)
            moved += lot.n
        if moved:
            self.m.transfers += 1
            self.m.transfer_units += moved
            self.m.unit_km += moved * self.w.dist[(mv.from_site, mv.to_site)]

    # --- serve and expire ---------------------------------------------------------------------------------------
    def _serve(self, d: int, record: bool) -> None:
        for h in self.w.hospitals:
            for c in Component:
                for g in recipient_groups(c):
                    key = (h.code, c, *g)
                    need = int(self.w.demand[key][d])
                    issued = 0
                    for dg in DONORS[(c, *g)]:
                        if need <= 0:
                            break
                        for lot in self.stock.take(h.code, c, dg, need, d):
                            need -= lot.n
                            issued += lot.n
                            if record:
                                self.m.age_at_issue_sum += lot.n * (d - lot.collected)
                    self.usage[key][d] = issued
                    if record:
                        self.m.issued += issued
                        if need > 0:
                            self.m.unmet += need
                            self.m.shortage_events += 1
                            self.m.unmet_by_component[c.value] += need
                            if g[1] is Rh.neg and c is not Component.plasma:
                                self.m.unmet_rh_neg += need
                                self.m.shortage_events_rh_neg += 1

    def _expire(self, d: int, record: bool) -> None:
        for key, lots in self.stock.lots.items():
            gone = sum(lot.n for lot in lots if lot.expiry <= d)
            if gone:
                self.stock.lots[key] = [lot for lot in lots if lot.expiry > d]
                if record:
                    self.m.expired += gone
                    self.m.expired_by_component[key[1].value] += gone

    def run(self) -> RunResult:
        warm = self.sc.warmup_days
        for d in range(self.days):
            record = d >= warm
            if d % 7 in self.gap:
                self._collect(d)
                self._orders(d)
            if self.policy != "A" and d >= warm:
                self._transfers(d)
            self._serve(d, record)
            self._expire(d, record)
        return RunResult(self.m.summary(), {"solver_seconds": round(self.solver_seconds, 2)}, self.stock, self.usage)


def run(world: World, policy: str, demand_k: float = K_UPPER) -> RunResult:
    return Simulation(world, policy, demand_k=demand_k).run()

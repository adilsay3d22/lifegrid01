"""Synthetic region from a scenario and a seed (FR-SIM-01). Same seed + scenario -> identical world. Never reads the clock."""

import math
from dataclasses import dataclass, field

import numpy as np

from app.core.enums import GROUPS, Abo, Component, Rh
from simulation.scenario import Scenario

CENTER = (23.78, 90.40)  # synthetic region; default time zone Asia/Dhaka (spec section 19)
# Mean daily units per hospital size (illustrative, not calibrated to any real hospital).
BASE_RATE = {
    Component.red_cells: {"small": 3.0, "medium": 8.0, "large": 18.0},
    Component.platelets: {"small": 0.6, "medium": 1.5, "large": 4.0},
    Component.plasma: {"small": 1.0, "medium": 3.0, "large": 7.0},
}
_PLACES = ["Riverside", "Lakeview", "Northgate", "Southfield", "Eastbank", "Westwood", "Hillcrest", "Meadowbrook",
           "Cedar Park", "Old Town", "Harbourside", "Greenway", "Stonebridge", "Elmhurst", "Bayview", "Fairmont"]
_KINDS = ["General Hospital", "Medical Centre", "District Hospital", "Teaching Hospital"]


@dataclass
class SimSite:
    code: str
    name: str
    type: str  # hospital | blood_bank
    lat: float
    lng: float
    size: str | None


@dataclass
class World:
    scenario: Scenario
    seed: int
    sites: list[SimSite]
    dist: dict[tuple[str, str], float]
    # Recipient demand per day. Plasma is ABO-only, stored under Rh.pos (rules ignore Rh for plasma).
    demand: dict[tuple[str, Component, Abo, Rh], np.ndarray]
    rate: dict[tuple[str, Component, Abo, Rh], float]  # expected daily demand (the planner's long-run view)
    donors: list[dict[str, object]] = field(default_factory=list)
    requests: list[dict[str, object]] = field(default_factory=list)

    @property
    def hospitals(self) -> list[SimSite]:
        return [s for s in self.sites if s.type == "hospital"]

    @property
    def banks(self) -> list[SimSite]:
        return [s for s in self.sites if s.type == "blood_bank"]


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def _point(rng: np.random.Generator, radius_km: float) -> tuple[float, float]:
    r, th = radius_km * math.sqrt(rng.random()), 2 * math.pi * rng.random()
    return (round(CENTER[0] + r * math.cos(th) / 111.0, 5), round(CENTER[1] + r * math.sin(th) / (111.0 * math.cos(math.radians(CENTER[0]))), 5))


def group_mix(sc: Scenario) -> dict[tuple[Abo, Rh], float]:
    m = {(Abo(k[:-1]), Rh.neg if k.endswith("-") else Rh.pos): v for k, v in sc.demand.group_mix.items()}
    total = sum(m.values())
    return {g: m.get(g, 0.0) / total for g in GROUPS}


def recipient_groups(c: Component) -> list[tuple[Abo, Rh]]:
    return [(a, Rh.pos) for a in Abo] if c is Component.plasma else list(GROUPS)


def generate(sc: Scenario, seed: int) -> World:
    rng = np.random.default_rng(seed)
    sites: list[SimSite] = []
    for i in range(sc.region.blood_banks):
        lat, lng = _point(rng, sc.region.radius_km * 0.3)
        sites.append(SimSite(f"BB-{i + 1:02d}", f"{_PLACES[i % len(_PLACES)]} Regional Blood Bank" + (f" {i // len(_PLACES) + 1}" if i >= len(_PLACES) else ""),
                             "blood_bank", lat, lng, None))
    sizes, probs = list(sc.site_size), np.array(list(sc.site_size.values()))
    for i in range(sc.region.sites):
        lat, lng = _point(rng, sc.region.radius_km)
        size = sizes[rng.choice(len(sizes), p=probs / probs.sum())]
        name = f"{_PLACES[(i + 3) % len(_PLACES)]} {_KINDS[i % len(_KINDS)]}" + (f" {i // len(_PLACES) + 1}" if i >= len(_PLACES) else "")
        sites.append(SimSite(f"H-{i + 1:02d}", name, "hospital", lat, lng, size))
    dist = {(a.code, b.code): round(haversine((a.lat, a.lng), (b.lat, b.lng)), 2) for a in sites for b in sites}

    days, mix = sc.days, group_mix(sc)
    week = np.array(sc.demand.weekly_pattern)[np.arange(days) % 7]  # day 0 is a Monday
    surge = np.ones(days)
    for dis in sc.disruptions:
        if dis.type == "demand_spike":
            surge[dis.start:dis.start + dis.days] *= dis.factor
    demand: dict[tuple[str, Component, Abo, Rh], np.ndarray] = {}
    rate: dict[tuple[str, Component, Abo, Rh], float] = {}
    for s in sites:
        if s.type != "hospital":
            continue
        spike = np.ones(days)
        for d in np.flatnonzero(rng.random(days) < sc.demand.spikes.probability_per_day):
            spike[d:d + sc.demand.spikes.duration_days] = sc.demand.spikes.multiplier
        for c in Component:
            base = BASE_RATE[c][s.size]  # type: ignore[index]
            for g in recipient_groups(c):
                share = mix[g] + (mix[(g[0], Rh.neg)] if c is Component.plasma else 0.0)
                lam = base * share * week * spike * surge
                demand[(s.code, c, *g)] = rng.poisson(lam).astype(np.int32)
                rate[(s.code, c, *g)] = base * share * float(np.mean(sc.demand.weekly_pattern))

    groups = list(mix)
    donors = [{"id": f"D{k:05d}", "group": groups[rng.choice(len(groups), p=np.array(list(mix.values())))],
               "area": tuple(round(v, 2) for v in _point(rng, sc.region.radius_km)), "reliability": round(float(rng.beta(3, 3)), 3)}
              for k in range(sc.donors.count)]
    urg = list(sc.requests.urgency_mix)
    requests = []
    hosp = [s.code for s in sites if s.type == "hospital"]
    for d in range(days):
        for _ in range(rng.poisson(sc.requests.per_week / 7)):
            requests.append({"day": d, "site": hosp[rng.integers(len(hosp))], "group": groups[rng.choice(len(groups), p=np.array(list(mix.values())))],
                             "units": int(rng.integers(1, 5)), "urgency": urg[rng.choice(len(urg), p=np.array(list(sc.requests.urgency_mix.values())))]})
    return World(sc, seed, sites, dist, demand, rate, donors, requests)

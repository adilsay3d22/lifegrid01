"""Scenario files (spec section 14): backend/simulation/scenarios/<name>.yaml."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

DIR = Path(__file__).parent / "scenarios"


class Region(BaseModel):
    sites: int = 12  # hospitals
    blood_banks: int = 2
    radius_km: float = 40


class Spikes(BaseModel):
    probability_per_day: float = 0.02
    multiplier: float = 3
    duration_days: int = 2


class Demand(BaseModel):
    model: Literal["poisson"] = "poisson"
    weekly_pattern: list[float] = Field(default=[1.1, 1.1, 1.0, 1.0, 1.0, 0.7, 0.6], min_length=7, max_length=7)
    group_mix: dict[str, float]
    spikes: Spikes = Spikes()


class Supply(BaseModel):
    deliveries_per_week: int = Field(3, ge=1, le=7)
    fill_rate: float = Field(0.95, gt=0, le=1)


class Donors(BaseModel):
    count: int = 3000
    base_accept_rate: float = 0.3
    no_show_rate: float = 0.15


class Requests(BaseModel):
    per_week: float = 6
    urgency_mix: dict[str, float] = {"emergency": 0.2, "urgent": 0.5, "routine": 0.3}


class Disruption(BaseModel):
    type: Literal["donation_drop", "transport_disruption", "demand_spike"]
    start: int
    days: int
    factor: float


class Scenario(BaseModel):
    name: str
    days: int = 180
    warmup_days: int = 56
    region: Region = Region()
    site_size: dict[Literal["small", "medium", "large"], float] = {"small": 0.5, "medium": 0.35, "large": 0.15}
    demand: Demand
    supply: Supply = Supply()
    donors: Donors = Donors()
    requests: Requests = Requests()
    disruptions: list[Disruption] = []
    forecast_noise: float = 0.0  # bad_forecast: multiplicative noise sd on forecasts used by policy C


def load(name: str) -> Scenario:
    return Scenario.model_validate(yaml.safe_load((DIR / f"{name}.yaml").read_text()))

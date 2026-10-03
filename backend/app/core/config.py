from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "dev-only-jwt-secret-change-me-0123456789"


class Settings(BaseSettings):
    """Infrastructure settings from the environment. Business rules live in BUSINESS_DEFAULTS / the `setting` table."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite:///./lifegrid.db"
    redis_url: str = "redis://localhost:6379/0"
    app_origin: str = "http://localhost:5173"

    jwt_secret: str = _DEV_SECRET
    # 32-byte keys, base64. Dev defaults are fixed so local data stays readable across restarts.
    phone_enc_key: str = "ZGV2LW9ubHktcGhvbmUtZW5jLWtleS0zMmJ5dGVzISE="
    phone_hash_key: str = "ZGV2LW9ubHktcGhvbmUtaGFzaC1rZXktMzJieXRlcyE="
    totp_enc_key: str = "ZGV2LW9ubHktdG90cC1zZWNyZXQta2V5LTMyYnl0ZSE="

    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 7
    cookie_secure: bool = True

    celery_always_eager: bool = False
    sms_provider: str = "mock"
    log_level: str = "INFO"

    def check(self) -> None:
        # "demo" is a hosted showcase: real secrets, but OTP codes on screen and the in-process scheduler (decision 0006).
        if self.env in ("production", "demo"):
            dev = Settings.model_fields
            for k in ("jwt_secret", "phone_enc_key", "phone_hash_key", "totp_enc_key"):
                if getattr(self, k) == dev[k].default:
                    raise RuntimeError(f"{k.upper()} must be set when ENV={self.env}")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.check()
    return s


# Business rules (spec section 6). Seeded into the `setting` table; admins change them there (FR-ADM-02).
# Clinical values are prototype placeholders and need clinician review before real use.
BUSINESS_DEFAULTS: dict[str, Any] = {
    "shelf_life_days": {"red_cells": 42, "platelets": 5, "plasma": 365},
    "min_transfer_life_days": {"red_cells": 5, "platelets": 1, "plasma": 30},
    "expiry_alert_days": {"red_cells": 3, "platelets": 1, "plasma": 14},
    "platelets_allow_out_of_group": True,
    "platelets_prefer_rh_match": True,
    "reservation_timeout_hours": 24,
    "plan_run_time": "02:00",
    "forecast_run_time": "01:30",
    "plan_horizon_days": 3,
    "solver_time_limit_s": 30,
    "optimizer_weights": {"expired": 1.0, "unmet": 10.0, "rh_neg_unmet_multiplier": 3.0, "unit_km": 0.01, "rank_step": 0.1, "lane": 0.5},
    "optimizer_demand_k": 0.5,
    "max_outgoing_lanes": 3,
    "lane_capacity_units": 40,
    "donor_cooldown_days": 120,
    "max_invites_per_30d": 2,
    "donor_age_min": 18,
    "donor_age_max": 60,
    "match_coverage_margin": 0.5,
    "match_score_weights": {"proximity": 0.40, "group_fit": 0.20, "reliability": 0.25, "fairness": 0.15},
    # Wait between waves, radius per wave (km); waves before escalation = len(radius_km) (spec 13.3)
    "match_waves": {
        "emergency": {"wait_minutes": 10, "radius_km": [5, 10, 20]},
        "urgent": {"wait_minutes": 30, "radius_km": [10, 20, 40]},
        "routine": {"wait_minutes": 120, "radius_km": [15, 30]},
    },
    "requester_open_limit": 3,
    "requester_daily_limit": 5,
    "stock_alert_days": 2,
    "appeal_default_hours": 72,
    "password_min_length": 12,
    "otp_ttl_minutes": 5,
    "otp_max_attempts": 5,
    "otp_lock_minutes": 15,
    "otp_requests_per_hour": 3,
}

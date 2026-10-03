"""`make seed`: load a demo region into the app database from a scenario (FR-SIM-03).

Runs the simulator through warm-up (policy A), then writes that state through the models: sites, synthetic staff,
current stock as units, usage history; then runs the nightly forecast and plan jobs. In-process rather than over HTTP
(decision 0002). Synthetic data only (SEC-17).
"""

import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

import app.models  # noqa: F401
from app.bootstrap import seed_reference
from app.core import security
from app.core.clock import now
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.core.enums import Abo, Availability, Rh, Role, SiteType, UnitStatus
from app.modules.audit import service as audit
from app.modules.auth.models import AppUser, UserSite
from app.modules.donors.models import Donor
from app.modules.forecasting import service as forecasting
from app.modules.forecasting.models import UsageDaily
from app.modules.inventory.models import BloodUnit, UnitMovement
from app.modules.redistribution import service as redistribution
from app.modules.sites.models import Site
from simulation.engine import Simulation
from simulation.generator import generate
from simulation.scenario import load

DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "synthetic-demo-pass")
DEMO_TOTP_SECRET = os.environ.get("DEMO_TOTP_SECRET", "LIFEGRIDDEMOSECRETKEYAAAAAAAAAAA")
STAFF = [  # synthetic accounts; match the web app's demo list
    ("nabila.karim@lifegrid.test", Role.bank_manager, "banks", False),
    ("tanvir.rahman@lifegrid.test", Role.hospital_lead, "H-01", False),
    ("farhana.siddiqui@lifegrid.test", Role.hospital_lead, "H-02,H-03", False),
    ("imran.chowdhury@lifegrid.test", Role.donor_coordinator, "", False),
    ("sadia.haque@lifegrid.test", Role.admin, "", True),
    ("mahmud.alam@lifegrid.test", Role.auditor, "", False),
]


DEMO_DONOR_PHONE = "+8801000000001"  # 10xx is not a mobile prefix in Bangladesh: synthetic numbers only (SEC-17)
DEMO_REQUESTER_PHONE = "+8801000009999"
SEED_DONORS = 400


def _seed_donors(db, world, sites, today):  # type: ignore[no-untyped-def]
    """Synthetic donors with phone logins. The first is a known, eligible O+ donor near H-01 for the demo."""
    import random

    rnd = random.Random(world.seed)
    enc = get_settings().phone_enc_key
    h01 = sites["H-01"]
    for i, d in enumerate(world.donors[:SEED_DONORS]):
        phone = DEMO_DONOR_PHONE if i == 0 else f"+88010000{10000 + i:05d}"
        user = AppUser(role=Role.donor, phone_hash=security.phone_hash(phone), phone_enc=security.encrypt(phone, enc))
        db.add(user)
        db.flush()
        abo, rh = d["group"] if i else (Abo.O, Rh.pos)
        lat, lng = (round(h01.lat + 0.01, 2), round(h01.lng, 2)) if i == 0 else d["area"]
        quiet = i > 0 and rnd.random() < 0.5
        db.add(Donor(user_id=user.id, abo=abo, rh=rh, group_verified=rnd.random() < 0.5, area_lat=lat, area_lng=lng,
                     birth_year=rnd.randint(1968, 2006) if i else 1994, weight_ok=i == 0 or rnd.random() < 0.95,
                     last_donation_on=None if i == 0 or rnd.random() < 0.4 else today - timedelta(days=rnd.randint(20, 400)),
                     availability=Availability.available if i == 0 or rnd.random() < 0.85 else Availability.unavailable,
                     quiet_start=time(22) if quiet else None, quiet_end=time(7) if quiet else None,
                     emergency_override=rnd.random() < 0.4, reliability=d["reliability"], consent_version="v1.2", consent_at=now()))
    db.add(AppUser(role=Role.requester, phone_hash=security.phone_hash(DEMO_REQUESTER_PHONE),
                   phone_enc=security.encrypt(DEMO_REQUESTER_PHONE, enc)))
    return SEED_DONORS


def seed_demo(scenario: str = "normal", seed: int = 42, create_schema: bool = False, quiet: bool = False) -> dict[str, int]:
    if create_schema:
        Base.metadata.create_all(engine)
    sc = load(scenario)
    world = generate(sc, seed)
    stop = sc.warmup_days
    sim = Simulation(world, "A", stop_day=stop)
    result = sim.run()

    with SessionLocal() as db:
        if db.scalar(select(Site).limit(1)) is not None:
            raise SystemExit("database already has sites; seed an empty database")
        seed_reference(db)
        sites = {s.code: Site(code=s.code, name=s.name, type=SiteType(s.type), lat=s.lat, lng=s.lng, area=s.name.split()[0]) for s in world.sites}
        db.add_all(sites.values())
        db.flush()
        banks = [s.id for s in sites.values() if s.type is SiteType.blood_bank]
        enc = get_settings().totp_enc_key
        for email, role, scope, totp in STAFF:
            ids = banks if scope == "banks" else [sites[c].id for c in scope.split(",") if c in sites]
            db.add(AppUser(email=email, role=role, password_hash=security.hash_password(DEMO_PASSWORD),
                           totp_secret_enc=security.encrypt(DEMO_TOTP_SECRET, enc) if totp else None,
                           sites=[UserSite(site_id=i) for i in ids]))

        tz = ZoneInfo("Asia/Dhaka")
        today = now().astimezone(tz).date()
        day0 = datetime.combine(today, time.min, tz)  # sim day `stop` == today

        def at(sim_day: int, hour: int = 0) -> datetime:
            return day0 + timedelta(days=sim_day - stop, hours=hour)

        seq, units = 0, 0
        for (code, comp, abo, rh), lots in result.stock.lots.items():
            for lot in lots:
                if lot.expiry < stop:
                    continue
                for _ in range(lot.n):
                    seq += 1
                    u = BloodUnit(unit_code=f"LG26-{seq:07d}", abo=abo, rh=rh, component=comp, collected_at=at(lot.collected, 9),
                                  expires_at=at(lot.expiry + 1), site_id=sites[code].id, status=UnitStatus.available)
                    db.add(u)
                    db.flush()
                    db.add(UnitMovement(unit_id=u.id, from_status=None, to_status=UnitStatus.available, to_site_id=u.site_id,
                                        reason="Received at site (demo seed)", created_at=min(at(lot.collected + 1, 10), now())))
                    units += 1
        rows = 0
        for (code, comp, abo, rh), arr in result.usage.items():
            for d in range(stop):
                if arr[d]:
                    db.add(UsageDaily(site_id=sites[code].id, day=today - timedelta(days=stop - d), component=comp, abo=abo, rh=rh,
                                      units_used=int(arr[d])))
                    rows += 1
        donors = _seed_donors(db, world, sites, today)
        audit.record(db, None, "demo.seed", "scenario", scenario, {"seed": seed, "sites": len(sites), "units": units, "donors": donors})
        db.commit()
        forecasting.run(db)
        plan = redistribution.run_plan(db)
    summary = {"sites": len(sites), "units": units, "usage_rows": rows}
    if not quiet:
        print(f"Seeded '{scenario}' (seed {seed}): {len(sites)} sites, {units} units, {rows} usage rows, plan {plan.id}")
        print(f"Staff sign-in: any account below, password {DEMO_PASSWORD!r}")
        for email, role, *_ in STAFF:
            print(f"  {email:34s} {role.value}")
        print(f"Admin authenticator secret (add to an authenticator app): {DEMO_TOTP_SECRET}")
        print(f"Phone app (/app): donor {DEMO_DONOR_PHONE}, requester {DEMO_REQUESTER_PHONE}; the code shows on screen in development")
    return summary

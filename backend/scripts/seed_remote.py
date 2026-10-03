"""One-time setup of the hosted demo database (docs/deploy.md).

Asks for the Neon connection string (input hidden), makes the app keys (kept in backend/deploy.env, git-ignored,
so re-runs reuse them), runs migrations and the demo seed, then prints the Vercel environment variables.
"""

import base64
import getpass
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT / "deploy.env"
NAMES = ("JWT_SECRET", "PHONE_ENC_KEY", "PHONE_HASH_KEY", "TOTP_ENC_KEY")


def keys() -> dict[str, str]:
    if KEYS.exists():
        return dict(line.split("=", 1) for line in KEYS.read_text().split())
    k = {n: base64.b64encode(os.urandom(32)).decode() for n in NAMES}
    KEYS.write_text("".join(f"{n}={v}\n" for n, v in k.items()))
    return k


def main() -> None:
    url = getpass.getpass("Neon connection string (input hidden): ").strip()
    url = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url)
    if "-pooler." not in url:
        sys.exit("Use the pooled string (Connect -> Connection pooling on; host contains -pooler).")
    direct = url.replace("-pooler.", ".")  # DDL over a direct connection, not PgBouncer
    env = {**os.environ, **keys(), "DATABASE_URL": direct, "ENV": "demo"}
    py = sys.executable
    subprocess.run([py, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)
    subprocess.run([py, "-m", "simulation", "seed"], cwd=ROOT, env=env, check=True)
    print("\nDatabase ready. Add these in Vercel -> Settings -> Environment Variables:\n")
    print(f"DATABASE_URL={url}")
    print("ENV=demo\nCELERY_ALWAYS_EAGER=true")
    for n, v in keys().items():
        print(f"{n}={v}")
    print(f"\n(keys saved in {KEYS}; keep that file private)")


if __name__ == "__main__":
    main()

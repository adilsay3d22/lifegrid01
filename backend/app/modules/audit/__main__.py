"""`python -m app.modules.audit verify` — recompute the hash chain (FR-AUD-02). Exit 1 if broken."""

import sys

from app.core.db import SessionLocal
from app.modules.audit.service import verify

if __name__ == "__main__":
    if sys.argv[1:] != ["verify"]:
        sys.exit("usage: python -m app.modules.audit verify")
    with SessionLocal() as db:
        r = verify(db)
    print(f"{'OK' if r.ok else 'BROKEN'}: {r.checked} events verified" + ("" if r.ok else f", first bad event #{r.broken_at}"))
    sys.exit(0 if r.ok else 1)

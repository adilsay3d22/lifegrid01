"""`python -m app.export_openapi` — write the OpenAPI schema for the frontend client generator (spec section 10)."""

import json
from pathlib import Path

from app.main import app

out = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=1))
print(f"wrote {out}")

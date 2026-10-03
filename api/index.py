"""Vercel entry point: the FastAPI app as one Python function. Requests reach it via the /api rewrite in vercel.json."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402,F401

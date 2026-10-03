@echo off
rem Local API without Docker: SQLite demo database (seed it first: python -m simulation seed --create-schema)
cd /d "%~dp0.."
if not defined DATABASE_URL set DATABASE_URL=sqlite:///./demo.db
set ENV=dev
rem No Celery workers locally: run jobs inline and let the API run the minute jobs (matching waves).
set CELERY_ALWAYS_EAGER=true
.venv\Scripts\python -m uvicorn app.main:app --port 8000

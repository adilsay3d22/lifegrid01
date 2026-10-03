# User manual

`../LifeGrid-User-Manual.pdf` is built from `manual.html` and the screenshots in `img/`.

To regenerate after UI changes (needs Microsoft Edge, which Playwright drives; no browser download):

```bash
cd backend && .venv/Scripts/pip install -e ".[docs]"
cd ../frontend
API_PROXY=http://localhost:8100 npx vite --mode live --port 5175 --strictPort   # live app, own terminal
npx vite build --outDir ../.manual-mock && npx vite preview --outDir ../.manual-mock --port 5176   # demo-mode app, own terminal
cd ../docs/manual
../../backend/.venv/Scripts/python capture.py   # seeds a fresh manual.db, serves it on :8100, takes 57 screenshots
../../backend/.venv/Scripts/python build.py     # writes ../LifeGrid-User-Manual.pdf with page-numbered contents
```

Edit the text in `manual.html`; screenshots are referenced as `img/<name>.png` (names are in `capture.py`).

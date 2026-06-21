"""Demo app: the V-Sentinel guardrail service + a browser UI.

The service itself (all the endpoints) lives in the library as
``vsentinel.server.create_app``. This module just builds it and adds the demo
web page at ``/``. Run with: ``uv run uvicorn api.main:app --port 8000``.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from vsentinel.server import create_app

# Load .env for the demo before the app reads any VSENTINEL_*/NEO4J_* vars.
# Demo-only convenience (the library never auto-loads .env); no-op if missing.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:
    pass

_WEB_DIR = Path(__file__).resolve().parents[1] / "web"
_INDEX = _WEB_DIR / "index.html"

# create_app builds + owns the sentinel (and closes its retriever on shutdown).
# We re-export the instance so tests can patch `sentinel.run`.
app = create_app()
app.mount("/static", StaticFiles(directory=str(_WEB_DIR / "static")), name="static")
sentinel = app.state.sentinel


@app.get("/", response_class=HTMLResponse)
def index():
    return _INDEX.read_text(encoding="utf-8")

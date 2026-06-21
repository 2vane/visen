"""Demo app: the V-Sentinel guardrail service + a browser UI.

The service itself (all the endpoints) lives in the library as
``vsentinel.server.create_app``. This module just builds it and adds the demo
web page at ``/``. Run with: ``uv run uvicorn api.main:app --port 8000``.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.responses import HTMLResponse

from vsentinel.server import build_default_sentinel, create_app

_WEB = Path(__file__).resolve().parents[1] / "web" / "index.html"

# Exposed module-level so tests can patch `sentinel.run` and reach the instance
# the routes use.
sentinel = build_default_sentinel()
app = create_app(sentinel)


@app.get("/", response_class=HTMLResponse)
def index():
    return _WEB.read_text(encoding="utf-8")

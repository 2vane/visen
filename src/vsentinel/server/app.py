"""The V-Sentinel guardrail HTTP service.

``create_app()`` returns a self-contained FastAPI app exposing the guardrail as
a service: ``/chat`` (native), the OpenAI-compatible (``/v1/...``) and
Ollama-native (``/api/...``) proxy endpoints, plus ``/health`` and the
``/recent`` monitor feed. It is part of the SDK, so ``vsentinel serve`` and a
``pip``-installed package both work without the demo app.

The demo (``api/main.py``) wraps this and adds the browser UI.
"""
from __future__ import annotations

import hmac
import logging
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from vsentinel.sentinel import Sentinel
from vsentinel.server import ollama_compat, openai_compat, store

LOGGER = logging.getLogger("vsentinel.server")

# Per-client fixed-window rate-limit state: client -> (window_start, count).
_RATE_BUCKETS: dict[str, tuple[float, int]] = {}
_RATE_LOCK = threading.Lock()
_WINDOW = 60.0


def build_default_sentinel() -> Sentinel:
    """Default: offline BM25. Set ``VSENTINEL_RETRIEVER=neo4j`` (with ``NEO4J_*``
    creds) to serve reranked citations over the legal-knowledge graph.

    The Neo4j path is wrapped so a missing config or a cold-start failure never
    crashes boot — it logs and degrades to BM25.
    """
    if os.environ.get("VSENTINEL_RETRIEVER", "").lower() == "neo4j":
        try:
            from vsentinel import FallbackRetriever, Neo4jConfig, Neo4jRetriever
            from vsentinel.retrieve import Retriever

            floor = float(os.environ.get("VSENTINEL_MIN_RERANK", "0.3"))
            neo = Neo4jRetriever(Neo4jConfig.from_env(min_reranker_score=floor))
            retriever = FallbackRetriever(neo, Retriever())
            # Warm the embedder/reranker + driver so the first request isn't
            # penalised by a cold load; FallbackRetriever swallows a failure.
            retriever.search("khởi động hệ thống", k=1)
            return Sentinel(retriever=retriever)
        except Exception:
            LOGGER.exception("Neo4j retriever unavailable; falling back to BM25.")
            return Sentinel()
    return Sentinel()


def _enforce_limits(
    request: Request,
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    """Optional, env-gated access control (both OFF by default).

    - ``VSENTINEL_API_KEY`` set => require a matching key, supplied either as the
      ``X-API-Key`` header or as ``Authorization: Bearer <key>`` (so OpenAI/Ollama
      chat clients pointed at the proxy can authenticate normally).
    - ``VSENTINEL_RATE_LIMIT=N`` (per minute, >0) => simple per-client throttle.
    """
    api_key = os.environ.get("VSENTINEL_API_KEY")
    if api_key:
        provided = x_api_key or ""
        if not provided and authorization and authorization.lower().startswith("bearer "):
            provided = authorization[7:].strip()
        if not hmac.compare_digest(provided, api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    try:
        limit = int(os.environ.get("VSENTINEL_RATE_LIMIT", "0") or "0")
    except ValueError:
        limit = 0
    if limit > 0:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with _RATE_LOCK:
            for ip in [ip for ip, (ws, _) in _RATE_BUCKETS.items() if now - ws >= _WINDOW]:
                del _RATE_BUCKETS[ip]
            window_start, count = _RATE_BUCKETS.get(client, (now, 0))
            count += 1
            _RATE_BUCKETS[client] = (window_start, count)
            exceeded = count > limit
        if exceeded:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


def create_app(sentinel: Sentinel | None = None) -> FastAPI:
    """Build the guardrail service. Pass a ``Sentinel`` to inject backends/config;
    otherwise a default (env-driven) one is built."""
    sentinel = sentinel or build_default_sentinel()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        close = getattr(sentinel._retriever, "close", None)
        if callable(close):
            close()

    app = FastAPI(title="V-Sentinel", lifespan=lifespan)
    app.state.sentinel = sentinel

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        LOGGER.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal error"})

    @app.post("/chat", dependencies=[Depends(_enforce_limits)])
    def chat(body: ChatIn):
        trace = sentinel.run(body.message)
        store.record("web", trace)
        LOGGER.info("chat decision=%s latency_ms=%s", trace.decision, trace.latency_ms)
        return trace

    @app.get("/recent")
    def recent(after: int = 0, limit: int = 50):
        return store.recent(after=after, limit=min(max(limit, 1), 100))

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "retriever": type(sentinel._retriever).__name__,
            "guard_model": sentinel.config.guard_model,
            "chat_model": sentinel.config.chat_model,
        }

    # Guardrail proxy: external chat clients route through here, not Ollama.
    # Same env-gated auth/rate-limit as /chat (else the controls are bypassable).
    app.include_router(
        openai_compat.build_router(sentinel, store.record),
        dependencies=[Depends(_enforce_limits)],
    )
    app.include_router(
        ollama_compat.build_router(sentinel, store.record),
        dependencies=[Depends(_enforce_limits)],
    )
    return app

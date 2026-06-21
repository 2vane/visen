from __future__ import annotations
import hmac
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from api import ollama_compat, openai_compat, store
from vsentinel import Sentinel

LOGGER = logging.getLogger("vsentinel.api")

_WEB = Path(__file__).resolve().parents[1] / "web" / "index.html"


def _build_sentinel() -> Sentinel:
    """Default: offline BM25. Set VSENTINEL_RETRIEVER=neo4j (with NEO4J_* creds)
    to serve real reranked citations over the legal-knowledge graph.

    The Neo4j path is wrapped so a missing config or a cold-start failure never
    crashes boot — it logs and degrades to BM25. Live request failures degrade
    through FallbackRetriever too."""
    if os.environ.get("VSENTINEL_RETRIEVER", "").lower() == "neo4j":
        try:
            from vsentinel import FallbackRetriever, Neo4jConfig, Neo4jRetriever
            from vsentinel.retrieve import Retriever

            # Relevance floor: the cross-encoder scores relevant legal units
            # ~0.7-1.0 and off-topic ones ~0.0, so 0.3 drops irrelevant
            # cross-law citations (returns no citation rather than a forced
            # wrong one). Env-tunable.
            floor = float(os.environ.get("VSENTINEL_MIN_RERANK", "0.3"))
            neo = Neo4jRetriever(Neo4jConfig.from_env(min_reranker_score=floor))
            retriever = FallbackRetriever(neo, Retriever())
            # Pre-load embedder/reranker + open the driver so the first real
            # request isn't penalised by a cold model load (~tens of seconds on
            # CPU). FallbackRetriever swallows a cold-start failure here.
            retriever.search("khởi động hệ thống", k=1)
            return Sentinel(retriever=retriever)
        except Exception:
            LOGGER.exception("Neo4j retriever unavailable; falling back to BM25.")
            return Sentinel()
    return Sentinel()


sentinel = _build_sentinel()

# Per-client fixed-window rate-limit state: client -> (window_start, count).
# Guarded by a lock since sync handlers run in a threadpool; pruned each request
# so the map can't grow unbounded with one-shot clients.
_RATE_BUCKETS: dict[str, tuple[float, int]] = {}
_RATE_LOCK = threading.Lock()
_WINDOW = 60.0


def _enforce_limits(
    request: Request, x_api_key: str | None = Header(default=None)
) -> None:
    """Optional, env-gated access control (both OFF by default).

    - VSENTINEL_API_KEY set => require a matching X-API-Key header.
    - VSENTINEL_RATE_LIMIT=N (per minute, >0) => simple per-client throttle.
    """
    api_key = os.environ.get("VSENTINEL_API_KEY")
    if api_key and not hmac.compare_digest(x_api_key or "", api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    try:
        limit = int(os.environ.get("VSENTINEL_RATE_LIMIT", "0") or "0")
    except ValueError:
        limit = 0
    if limit > 0:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with _RATE_LOCK:
            # Evict expired windows (incl. this client's own, so it resets).
            for ip in [ip for ip, (ws, _) in _RATE_BUCKETS.items() if now - ws >= _WINDOW]:
                del _RATE_BUCKETS[ip]
            window_start, count = _RATE_BUCKETS.get(client, (now, 0))
            count += 1
            _RATE_BUCKETS[client] = (window_start, count)
            exceeded = count > limit
        if exceeded:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close = getattr(sentinel._retriever, "close", None)
    if callable(close):
        close()


app = FastAPI(title="V-Sentinel", lifespan=lifespan)
# Guardrail proxy: external chat UIs can route through here (OpenAI- and
# Ollama-native wire formats), so any client points at this server, not Ollama.
app.include_router(openai_compat.build_router(sentinel, store.record))
app.include_router(ollama_compat.build_router(sentinel, store.record))


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    """Never leak a stack trace to the client; log it server-side instead."""
    LOGGER.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal error"})


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


@app.post("/chat", dependencies=[Depends(_enforce_limits)])
def chat(body: ChatIn):
    trace = sentinel.run(body.message)
    store.record("web", trace)
    LOGGER.info("chat decision=%s latency_ms=%s", trace.decision, trace.latency_ms)
    return trace


@app.get("/recent")
def recent(after: int = 0, limit: int = 50):
    """Recent decisions (any source) for the live-monitor dashboard."""
    return store.recent(after=after, limit=min(max(limit, 1), 100))


@app.get("/health")
def health():
    return {
        "status": "ok",
        "retriever": type(sentinel._retriever).__name__,
        "guard_model": sentinel.config.guard_model,
        "chat_model": sentinel.config.chat_model,
    }


@app.get("/", response_class=HTMLResponse)
def index():
    return _WEB.read_text(encoding="utf-8")

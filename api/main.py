from __future__ import annotations
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from vsentinel import Sentinel

_WEB = Path(__file__).resolve().parents[1] / "web" / "index.html"


def _build_sentinel() -> Sentinel:
    """Default: offline BM25. Set VSENTINEL_RETRIEVER=neo4j (with NEO4J_* creds)
    to serve real reranked citations over the legal-knowledge graph."""
    if os.environ.get("VSENTINEL_RETRIEVER", "").lower() == "neo4j":
        from vsentinel import Neo4jRetriever

        retriever = Neo4jRetriever()
        # Pre-load embedder/reranker + open the driver so the first real request
        # isn't penalised by a cold model load (~tens of seconds on CPU).
        retriever.search("khởi động hệ thống", k=1)
        return Sentinel(retriever=retriever)
    return Sentinel()


sentinel = _build_sentinel()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close = getattr(sentinel._retriever, "close", None)
    if callable(close):
        close()


app = FastAPI(title="V-Sentinel", lifespan=lifespan)


class ChatIn(BaseModel):
    message: str


@app.post("/chat")
def chat(body: ChatIn):
    return sentinel.run(body.message)


@app.get("/", response_class=HTMLResponse)
def index():
    return _WEB.read_text(encoding="utf-8")

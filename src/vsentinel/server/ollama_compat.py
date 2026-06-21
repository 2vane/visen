"""Ollama-native chat endpoint, so Ollama-style clients (Enchanted, …) can route
through V-Sentinel as a guardrail proxy.

Mirrors ``vsentinel.server.openai_compat`` but speaks Ollama's wire format: ``/api/chat``
(NDJSON streaming, the Ollama default), ``/api/tags`` for model discovery, and
``/api/version``. Same scope: the guardrail acts on the latest user message and
streaming replays the already-screened text.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from vsentinel.server.proxy_common import ChatMessage, last_user_message

_CHUNK = 24


class OllamaChatIn(BaseModel):
    model: str | None = None
    messages: list[ChatMessage] = []
    stream: bool = True  # Ollama streams by default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _message_obj(content: str) -> dict:
    return {"role": "assistant", "content": content}


def _final(model: str, content: str) -> dict:
    return {
        "model": model,
        "created_at": _now(),
        "message": _message_obj(content),
        "done": True,
        "done_reason": "stop",
    }


def _ndjson(content: str, model: str):
    def line(obj: dict) -> str:
        return json.dumps(obj, ensure_ascii=False) + "\n"

    for i in range(0, len(content), _CHUNK):
        yield line(
            {
                "model": model,
                "created_at": _now(),
                "message": _message_obj(content[i : i + _CHUNK]),
                "done": False,
            }
        )
    yield line({**_final(model, ""), "message": _message_obj("")})


def build_router(sentinel, record) -> APIRouter:
    """Wire the Ollama shim to a Sentinel instance and a ``record(source, trace)``."""
    router = APIRouter()

    @router.get("/api/tags")
    def tags():
        model = sentinel.config.chat_model
        return {
            "models": [
                {
                    "name": model,
                    "model": model,
                    "modified_at": _now(),
                    "size": 0,
                    "digest": "",
                    "details": {"family": "vsentinel", "parameter_size": "", "quantization_level": ""},
                }
            ]
        }

    @router.get("/api/version")
    def version():
        return {"version": "v-sentinel-proxy"}

    @router.post("/api/chat")
    def chat(body: OllamaChatIn):
        model = body.model or sentinel.config.chat_model
        user = last_user_message(body.messages)
        if not user.strip():
            content = "Xin gửi một câu hỏi để tôi có thể hỗ trợ."
        else:
            trace = sentinel.run(user)
            record("ollama", trace)
            content = trace.final_message or ""
        if body.stream:
            return StreamingResponse(_ndjson(content, model), media_type="application/x-ndjson")
        return _final(model, content)

    return router

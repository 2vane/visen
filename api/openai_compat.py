"""OpenAI-compatible chat endpoint, so V-Sentinel can sit in front of Ollama as
a transparent guardrail proxy.

Point any OpenAI-style chat client (Open WebUI, LibreChat, ...) at this server's
base URL: each turn is run through the full Sentinel pipeline (input screening →
guarded generation via the configured chatbot → output screening) and the
*screened* answer is returned in OpenAI's response shape.

Scope (intentionally minimal for the demo): the guardrail acts on the latest
user message; prior turns are not replayed to the model. Streaming replays the
already-screened text, so output screening integrity is preserved.
"""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.proxy_common import ChatMessage, last_user_message

_CHUNK = 24  # chars per streamed delta


class ChatCompletionIn(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None
    stream: bool = False


def _completion(content: str, model: str) -> dict:
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _sse(content: str, model: str):
    cid = "chatcmpl-" + uuid.uuid4().hex
    created = int(time.time())

    def chunk(delta: dict, finish=None) -> str:
        payload = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

    yield chunk({"role": "assistant"})
    for i in range(0, len(content), _CHUNK):
        yield chunk({"content": content[i : i + _CHUNK]})
    yield chunk({}, "stop")
    yield "data: [DONE]\n\n"


def build_router(sentinel, record) -> APIRouter:
    """Wire the proxy to a Sentinel instance and a ``record(source, trace)`` sink."""
    router = APIRouter()

    @router.get("/v1/models")
    def models():
        return {
            "object": "list",
            "data": [
                {"id": sentinel.config.chat_model, "object": "model", "owned_by": "v-sentinel"}
            ],
        }

    @router.post("/v1/chat/completions")
    def chat_completions(body: ChatCompletionIn):
        model = body.model or sentinel.config.chat_model
        user = last_user_message(body.messages)
        if not user.strip():
            content = "Xin gửi một câu hỏi để tôi có thể hỗ trợ."
        else:
            trace = sentinel.run(user)
            record("openai", trace)
            content = trace.final_message or ""
        if body.stream:
            return StreamingResponse(_sse(content, model), media_type="text/event-stream")
        return _completion(content, model)

    return router

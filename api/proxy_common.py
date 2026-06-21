"""Shared request bits for the guardrail proxy endpoints (OpenAI + Ollama).

Both proxies accept a chat-style ``messages`` list and guard the latest user
turn, so the message model and extraction live here once.
"""
from __future__ import annotations

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str | None = ""


def last_user_message(messages: list[ChatMessage]) -> str:
    """The most recent user message content, or ``""`` if there is none."""
    for m in reversed(messages):
        if m.role == "user" and m.content:
            return m.content
    return ""

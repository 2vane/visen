from __future__ import annotations
from typing import Literal
from vsentinel.ollama_client import chat, OllamaError

GUARD_MODEL = "qwen3guard"
_PROMPT = (
    "You are a safety classifier. Classify the following {role} message. "
    "Reply with exactly one word: Safe, Controversial, or Unsafe.\n\nMessage:\n{text}"
)


def classify(
    text: str,
    role: Literal["user", "assistant"] = "user",
    timeout: float = 15,
    model: str = GUARD_MODEL,
    base_url: str | None = None,
) -> str:
    try:
        out = chat(
            model,
            [{"role": "user", "content": _PROMPT.format(role=role, text=text)}],
            timeout=timeout,
            base_url=base_url,
        )
    except OllamaError:
        return "controversial"
    low = out.lower()
    if "unsafe" in low:
        return "unsafe"
    if "safe" in low:
        return "safe"
    if "controversial" in low:
        return "controversial"
    return "controversial"

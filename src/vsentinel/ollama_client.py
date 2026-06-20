from __future__ import annotations
import os
import httpx


class OllamaError(Exception):
    pass


def _base_url(base_url: str | None = None) -> str:
    if base_url:
        return base_url
    return os.environ.get("VSENTINEL_OLLAMA_URL", "http://localhost:11434")


def chat(
    model: str,
    messages: list[dict],
    options: dict | None = None,
    timeout: float = 30,
    base_url: str | None = None,
) -> str:
    payload = {"model": model, "messages": messages, "stream": False}
    if options:
        payload["options"] = options
    try:
        resp = httpx.post(f"{_base_url(base_url)}/api/chat", json=payload, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise OllamaError(str(exc)) from exc
    return resp.json().get("message", {}).get("content", "")

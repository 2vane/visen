from __future__ import annotations
import os
import time
import httpx

# Transient failures worth one quick retry (connection refused mid-restart,
# a slow first response). Other HTTP errors are returned to the caller at once.
_TRANSIENT = (httpx.ConnectError, httpx.TimeoutException)
_BACKOFF = 0.5


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
    retries: int = 1,
) -> str:
    payload = {"model": model, "messages": messages, "stream": False}
    if options:
        payload["options"] = options
    url = f"{_base_url(base_url)}/api/chat"
    attempts = max(0, retries) + 1
    for attempt in range(attempts):
        try:
            resp = httpx.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")
        except _TRANSIENT as exc:
            if attempt + 1 >= attempts:
                raise OllamaError(str(exc)) from exc
            time.sleep(_BACKOFF)
        except httpx.HTTPError as exc:
            raise OllamaError(str(exc)) from exc

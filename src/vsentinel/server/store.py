"""In-memory ring buffer of recent decisions.

Lets the web page act as a live *monitor*: every guarded turn — whether it came
from the built-in UI or an external chat client via the OpenAI-compatible proxy
— is recorded here, and the dashboard polls ``/recent`` to display it. Bounded
and thread-safe (sync handlers run in a threadpool).
"""
from __future__ import annotations

import threading
from collections import deque

_MAX = 100
_LOCK = threading.Lock()
_EVENTS: deque[dict] = deque(maxlen=_MAX)
_SEQ = 0


def record(source: str, trace) -> None:
    """Append a decision. ``source`` tags the origin (e.g. ``web``/``openai``)."""
    global _SEQ
    data = trace.model_dump() if hasattr(trace, "model_dump") else dict(trace)
    with _LOCK:
        _SEQ += 1
        _EVENTS.append({"seq": _SEQ, "source": source, "trace": data})


def recent(after: int = 0, limit: int = 50) -> list[dict]:
    """Decisions with ``seq > after`` (for incremental polling), newest-trimmed."""
    with _LOCK:
        items = [e for e in _EVENTS if e["seq"] > after]
    return items[-limit:]

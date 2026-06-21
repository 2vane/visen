"""Per-app ring buffer of recent decisions.

Lets the web page act as a live *monitor*: every guarded turn — from the
built-in UI or an external chat client via the proxy — is recorded here, and the
dashboard polls ``/recent`` to display it. Each ``create_app()`` owns its own
``Store`` so multiple apps in one process don't share a feed. Bounded and
thread-safe (sync handlers run in a threadpool).
"""
from __future__ import annotations

import threading
from collections import deque


class Store:
    def __init__(self, maxlen: int = 100) -> None:
        self._events: deque[dict] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._seq = 0

    def record(self, source: str, trace) -> None:
        """Append a decision. ``source`` tags the origin (e.g. ``web``/``openai``)."""
        data = trace.model_dump() if hasattr(trace, "model_dump") else dict(trace)
        with self._lock:
            self._seq += 1
            self._events.append({"seq": self._seq, "source": source, "trace": data})

    def recent(self, after: int = 0, limit: int = 50) -> list[dict]:
        """Decisions with ``seq > after`` (for incremental polling), newest-trimmed."""
        with self._lock:
            items = [e for e in self._events if e["seq"] > after]
        return items[-limit:]

"""A retriever that degrades to a backup when the primary fails.

Wraps a primary retriever (e.g. ``Neo4jRetriever``) and a fallback (e.g. the
offline BM25 ``Retriever``). If the primary raises for any reason — connection
loss, an offline index, a model that fails to load — the search transparently
falls back so the guardrail keeps citing *something* instead of crashing the
whole request. Both collaborators only need ``.search(query, k) -> list``.
"""
from __future__ import annotations

import logging

LOGGER = logging.getLogger("vsentinel.retrievers.fallback")


class FallbackRetriever:
    def __init__(self, primary, fallback) -> None:
        self.primary = primary
        self.fallback = fallback

    def search(self, query: str, k: int = 2):
        try:
            return self.primary.search(query, k)
        except Exception as exc:  # any primary failure => degrade, never crash
            LOGGER.warning(
                "Primary retriever failed (%s); falling back to backup.", exc
            )
            return self.fallback.search(query, k)

    def close(self) -> None:
        for retriever in (self.primary, self.fallback):
            close = getattr(retriever, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:  # best-effort cleanup
                    LOGGER.warning("Error closing retriever: %s", exc)

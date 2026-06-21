"""A retriever that uses two backends *together* (not just as a fallback).

Wraps a vector retriever (e.g. ``Neo4jRetriever``) and a lexical one (e.g. the
offline BM25 ``Retriever``) and interleaves their hits — so a query benefits
from both Neo4j's semantic vector search and BM25's exact-term matching. If one
backend raises (connection loss, offline index, model load failure), the search
degrades to whichever still works instead of crashing the request.

Both collaborators only need ``.search(query, k) -> list[Article]``.
"""
from __future__ import annotations

import logging

LOGGER = logging.getLogger("vsentinel.retrievers.hybrid")


class HybridRetriever:
    """Vector (primary) + lexical (secondary) retrieval, interleaved and deduped."""

    def __init__(self, primary, secondary) -> None:
        self.primary = primary
        self.secondary = secondary

    def _safe_search(self, retriever, query: str, k: int) -> list:
        try:
            return list(retriever.search(query, k))
        except Exception as exc:  # one backend down must not sink the query
            LOGGER.warning("%s failed (%s); using the other backend only.",
                           type(retriever).__name__, exc)
            return []

    def search(self, query: str, k: int = 2):
        # Pull k from each so the merge has enough to fill k after dedup.
        primary = self._safe_search(self.primary, query, k)
        secondary = self._safe_search(self.secondary, query, k)

        merged: list = []
        seen: set[tuple[str, str]] = set()
        # Interleave so both backends contribute (vector hit, lexical hit, …).
        for i in range(max(len(primary), len(secondary))):
            for hits in (primary, secondary):
                if i < len(hits):
                    art = hits[i]
                    key = (getattr(art, "source", ""), getattr(art, "ref", ""))
                    if key not in seen:
                        seen.add(key)
                        merged.append(art)
        return merged[:k]

    def close(self) -> None:
        for retriever in (self.primary, self.secondary):
            close = getattr(retriever, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:  # best-effort cleanup
                    LOGGER.warning("Error closing retriever: %s", exc)

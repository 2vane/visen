"""Convenience ``run(text) -> DecisionTrace`` over a shared Sentinel.

This used to be a second copy of the staged pipeline. It now delegates to a
module-level :class:`~vsentinel.sentinel.Sentinel` so the eval harness and the
NeMo rails action measure exactly the hardened path the demo runs — one source
of truth, no divergence.
"""
from __future__ import annotations

from vsentinel.schema import DecisionTrace
from vsentinel.sentinel import Sentinel

# Built lazily on first use so importing this module has no side effects (no disk
# I/O, no backend config) and env overrides set before the first call are honored.
# Tests patch `_SENTINEL` directly to inject offline backends.
_SENTINEL: Sentinel | None = None


def _get_sentinel() -> Sentinel:
    global _SENTINEL
    if _SENTINEL is None:
        _SENTINEL = Sentinel()
    return _SENTINEL


def run(user_text: str) -> DecisionTrace:
    return _get_sentinel().run(user_text)

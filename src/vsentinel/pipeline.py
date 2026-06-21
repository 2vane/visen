"""Convenience ``run(text) -> DecisionTrace`` over a shared Sentinel.

This used to be a second copy of the staged pipeline. It now delegates to a
module-level :class:`~vsentinel.sentinel.Sentinel` so the eval harness and the
NeMo rails action measure exactly the hardened path the demo runs — one source
of truth, no divergence.
"""
from __future__ import annotations

from vsentinel.schema import DecisionTrace
from vsentinel.sentinel import Sentinel

_SENTINEL = Sentinel()


def run(user_text: str) -> DecisionTrace:
    return _SENTINEL.run(user_text)

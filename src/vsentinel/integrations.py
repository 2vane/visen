"""Helpers to add V-Sentinel guardrails to an existing chatbot/agent.

Keep this module dependency-light (no FastAPI/web imports) so it can be used
anywhere. For an ASGI/FastAPI integration, see `api/main.py` and `examples/`.
"""
from __future__ import annotations

import functools
from typing import Callable

from vsentinel.sentinel import Sentinel

Chat = Callable[[str], str]


def wrap(chat_fn: Chat, sentinel: Sentinel | None = None) -> Chat:
    """Wrap a ``f(message) -> reply`` chatbot with input + output guardrails.

    Blocked input returns the refusal message without ever calling ``chat_fn``.
    For allowed/reframed input, ``chat_fn`` is called and its reply is screened
    (PII redacted / unsafe blocked) before being returned.
    """
    s = sentinel or Sentinel()

    @functools.wraps(chat_fn)
    def wrapped(message: str) -> str:
        trace = s.check_input(message)
        if trace.decision == "BLOCK":
            return trace.final_message
        reply = chat_fn(message)
        _, final_text = s.check_output(reply)
        return final_text

    return wrapped


def guard(sentinel: Sentinel | None = None):
    """Decorator form of :func:`wrap`.

    Usage::

        @guard()                 # default Sentinel
        def chat(message): ...

        @guard(my_sentinel)      # custom config/backends
        def chat(message): ...
    """

    def deco(chat_fn: Chat) -> Chat:
        return wrap(chat_fn, sentinel)

    return deco

"""Pluggable LLM backends for V-Sentinel.

Consumers can plug in any classifier / chatbot (OpenAI, Anthropic, local, …)
by passing callables that satisfy the :class:`Classifier` / :class:`Chatbot`
protocols. The defaults wrap a local Ollama install.
"""
from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from vsentinel import generate, guard_client

Severity = Literal["safe", "controversial", "unsafe"]


@runtime_checkable
class Classifier(Protocol):
    """Scores a message's safety. MUST fail safe (never silently 'safe')."""

    def __call__(self, text: str, role: Literal["user", "assistant"] = "user") -> Severity: ...


@runtime_checkable
class Chatbot(Protocol):
    """Generates a reply given the user text, a safety directive, and legal context."""

    def __call__(self, user_text: str, safety_directive: str, articles: list) -> str: ...


class OllamaClassifier:
    """Default classifier via Ollama (safe/controversial/unsafe).

    Designed for Qwen3Guard-Gen, but it is not on the Ollama registry, so the
    default model is ``qwen2.5`` (the classifier prompt is model-agnostic).
    """

    def __init__(self, model: str = "qwen2.5", base_url: str | None = None, timeout: float = 15):
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    def __call__(self, text: str, role: Literal["user", "assistant"] = "user") -> Severity:
        return guard_client.classify(
            text, role=role, timeout=self.timeout, model=self.model, base_url=self.base_url
        )


class OllamaChatbot:
    """Default chatbot: Qwen2.5 via Ollama, with safety directive + legal context."""

    def __init__(self, model: str = "qwen2.5", base_url: str | None = None):
        self.model = model
        self.base_url = base_url

    def __call__(self, user_text: str, safety_directive: str, articles: list) -> str:
        return generate.answer(
            user_text, safety_directive, articles, model=self.model, base_url=self.base_url
        )

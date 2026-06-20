"""Configuration for the Sentinel guardrail facade."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SentinelConfig:
    """Tunable settings for a :class:`vsentinel.sentinel.Sentinel` instance.

    All fields have sane defaults targeting a local Ollama install, so
    ``SentinelConfig()`` works out of the box. Override what you need.
    """

    # Default Ollama backend settings (ignored if you inject custom backends).
    ollama_url: str = "http://localhost:11434"
    chat_model: str = "qwen2.5"
    guard_model: str = "qwen3guard"

    # Decision tuning.
    attack_threshold: float = 0.8  # rule_score >= this => 'attack'
    retrieve_k: int = 2            # legal articles retrieved for grounding/citation

    # Optional resource override (None => packaged default decree articles).
    articles_path: str | None = None

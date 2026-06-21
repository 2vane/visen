"""Configuration for the Sentinel guardrail facade."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class SentinelConfig:
    """Tunable settings for a :class:`vsentinel.sentinel.Sentinel` instance.

    All fields have sane defaults targeting a local Ollama install, so
    ``SentinelConfig()`` works out of the box. Override what you need.

    The Ollama URL and model names also read environment variables so a
    deployment/demo can point them without code changes:
    ``VSENTINEL_OLLAMA_URL``, ``VSENTINEL_CHAT_MODEL``, ``VSENTINEL_GUARD_MODEL``.
    (e.g. set ``VSENTINEL_GUARD_MODEL=qwen2.5`` when no dedicated guard model is
    installed — the classifier prompt is model-agnostic.)
    """

    # Default Ollama backend settings (ignored if you inject custom backends).
    ollama_url: str = field(
        default_factory=lambda: os.environ.get("VSENTINEL_OLLAMA_URL", "http://localhost:11434")
    )
    chat_model: str = field(
        default_factory=lambda: os.environ.get("VSENTINEL_CHAT_MODEL", "qwen2.5")
    )
    guard_model: str = field(
        default_factory=lambda: os.environ.get("VSENTINEL_GUARD_MODEL", "qwen2.5")
    )

    # Decision tuning.
    attack_threshold: float = 0.8  # rule_score >= this => 'attack'
    retrieve_k: int = 2            # legal articles retrieved for grounding/citation

    # Optional resource override (None => packaged default decree articles).
    articles_path: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.attack_threshold <= 1.0:
            raise ValueError(
                f"attack_threshold phải trong [0.0, 1.0], nhận {self.attack_threshold!r}"
            )
        if self.retrieve_k < 1:
            raise ValueError(f"retrieve_k phải >= 1, nhận {self.retrieve_k!r}")
        if not (self.ollama_url.startswith("http://") or self.ollama_url.startswith("https://")):
            raise ValueError(
                f"ollama_url phải bắt đầu bằng http:// hoặc https://, nhận {self.ollama_url!r}"
            )

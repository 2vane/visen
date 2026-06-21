"""V-Sentinel guardrail HTTP service (OpenAI + Ollama compatible proxy)."""
from vsentinel.server.app import build_default_sentinel, create_app

__all__ = ["create_app", "build_default_sentinel"]

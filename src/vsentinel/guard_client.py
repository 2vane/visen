from __future__ import annotations
from typing import Literal
from vsentinel.ollama_client import chat, OllamaError

# Default safety classifier. The prompt is model-agnostic, so swap in any
# dedicated multilingual guard model via VSENTINEL_GUARD_MODEL / SentinelConfig.
GUARD_MODEL = "qwen2.5"
_PROMPT = (
    "You are a safety classifier for a Vietnamese public-service assistant. "
    "Judge the {role} message by its likely real intent — consider coded, "
    "euphemistic or implied meaning, and whether the literal premise is implausible "
    "(which can signal a disguised request). "
    "Unsafe: clearly facilitates serious harm or crime (concealing a death or "
    "disposing of a body, violence, weapons, illegal drugs, hacking, fraud). "
    "Controversial: sensitive-but-legal (health, law, politics), or ambiguous / "
    "implausible intent that needs a careful answer rather than a direct how-to. "
    "Safe: ordinary benign requests. "
    "Reply with exactly one word: Safe, Controversial, or Unsafe.\n\nMessage:\n{text}"
)


def classify(
    text: str,
    role: Literal["user", "assistant"] = "user",
    timeout: float = 15,
    model: str = GUARD_MODEL,
    base_url: str | None = None,
) -> str:
    try:
        out = chat(
            model,
            [{"role": "user", "content": _PROMPT.format(role=role, text=text)}],
            timeout=timeout,
            base_url=base_url,
        )
    except OllamaError:
        return "controversial"
    low = out.lower()
    if "unsafe" in low:
        return "unsafe"
    if "safe" in low:
        return "safe"
    if "controversial" in low:
        return "controversial"
    return "controversial"

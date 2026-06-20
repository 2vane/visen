from __future__ import annotations
from vsentinel.ollama_client import chat, OllamaError

_FALLBACK = "Xin lỗi, hệ thống tạm thời không thể trả lời. Vui lòng thử lại sau."


def answer(
    user_text: str,
    safety_directive: str,
    articles: list,
    model: str = "qwen2.5",
    base_url: str | None = None,
) -> str:
    context = "\n".join(f"- {a.ref}: {a.snippet}" for a in articles)
    system = "Bạn là trợ lý dịch vụ công Việt Nam, trả lời bằng tiếng Việt."
    if safety_directive:
        system += "\n" + safety_directive
    if context:
        system += f"\n\nCĂN CỨ PHÁP LÝ LIÊN QUAN:\n{context}"
    try:
        return chat(model, [{"role": "system", "content": system},
                            {"role": "user", "content": user_text}], base_url=base_url)
    except OllamaError:
        return _FALLBACK

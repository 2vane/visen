"""Custom backend: wrap a third-party LLM SDK as Sentinel's classifier + chatbot.

This file shows the integration pattern with pseudocode SDK calls.
Swap the SDK import and call sites for your actual provider.

Supported providers follow the same two-callable pattern — only the SDK call
differs.  The rest (Sentinel construction, pipeline usage) is identical.

Run (after filling in your SDK + credentials):
    uv run python examples/custom_backend.py
"""
from vsentinel import Sentinel, SentinelConfig

# ---------------------------------------------------------------------------
# EXAMPLE A: Anthropic Claude as the classifier
# ---------------------------------------------------------------------------
# import anthropic  # pip install anthropic
#
# _anthropic = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
#
# GUARD_SYSTEM = (
#     "You are a content safety classifier. "
#     "Reply with EXACTLY one word: safe, controversial, or unsafe."
# )
#
# def anthropic_classifier(text: str, role: str = "user") -> str:
#     resp = _anthropic.messages.create(
#         model="claude-opus-4-5",
#         max_tokens=5,
#         system=GUARD_SYSTEM,
#         messages=[{"role": "user", "content": text}],
#     )
#     verdict = resp.content[0].text.strip().lower()
#     # Fail safe: anything unexpected → controversial
#     return verdict if verdict in {"safe", "controversial", "unsafe"} else "controversial"

# ---------------------------------------------------------------------------
# EXAMPLE B: OpenAI GPT as the chatbot
# ---------------------------------------------------------------------------
# import openai  # pip install openai
#
# _openai = openai.OpenAI()  # reads OPENAI_API_KEY from env
#
# def openai_chatbot(user_text: str, safety_directive: str, articles: list) -> str:
#     article_ctx = "\n".join(a.snippet for a in articles if a.snippet)
#     system = f"{safety_directive}\n\nContext:\n{article_ctx}" if article_ctx else safety_directive
#     resp = _openai.chat.completions.create(
#         model="gpt-4o",
#         messages=[
#             {"role": "system", "content": system},
#             {"role": "user",   "content": user_text},
#         ],
#     )
#     return resp.choices[0].message.content

# ---------------------------------------------------------------------------
# Wire them into Sentinel
# ---------------------------------------------------------------------------
# config = SentinelConfig(
#     attack_threshold=0.8,
#     retrieve_k=2,
#     # ollama_url / chat_model / guard_model are ignored when you inject callables
# )
# sentinel = Sentinel(
#     config=config,
#     classifier=anthropic_classifier,   # swap for any callable (text, role) -> severity
#     chatbot=openai_chatbot,            # swap for any callable (text, directive, articles) -> str
# )
#
# trace = sentinel.run("Giờ làm việc của bệnh viện?")
# print(trace.decision, trace.final_message)

# ---------------------------------------------------------------------------
# Protocol summary (copy-paste template for any LLM)
# ---------------------------------------------------------------------------
#
# classifier: (text: str, role: str = "user") -> Literal["safe", "controversial", "unsafe"]
#   MUST fail safe: on error / unexpected output → return "controversial", never silently "safe"
#
# chatbot:    (user_text: str, safety_directive: str, articles: list[Article]) -> str
#   safety_directive is a ready-to-use system-prompt string injected by the policy engine.
#   articles is a list of vsentinel.schema.Article objects (fields: ref, snippet).
#
# Both callables are plain Python — no base class to inherit, no registration step.

print(
    "This file is a template. Uncomment the SDK sections and fill in credentials "
    "to use a real third-party LLM as a V-Sentinel backend."
)

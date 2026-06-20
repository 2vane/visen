from __future__ import annotations
from vsentinel.pipeline import run

def vsentinel_guard(context: dict) -> dict:
    user_message = context.get("user_message", "")
    trace = run(user_message)
    return {"decision": trace.decision, "final_message": trace.final_message}

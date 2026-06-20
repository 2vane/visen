from __future__ import annotations
from vsentinel.pipeline import run

def vsentinel_guard(user_message: str = "") -> dict:
    trace = run(user_message)
    return {"decision": trace.decision, "final_message": trace.final_message}

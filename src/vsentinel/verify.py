from __future__ import annotations
from vsentinel.guard_client import classify
from vsentinel.pii import detect_pii, redact
from vsentinel.schema import OutputCheck

_BLOCKED_MSG = "Phản hồi đã bị chặn do vi phạm chính sách an toàn."


def check_output(answer: str) -> tuple[OutputCheck, str]:
    if classify(answer, role="assistant") == "unsafe":
        return OutputCheck(verdict="BLOCK"), _BLOCKED_MSG
    hits = detect_pii(answer)
    if hits:
        return OutputCheck(verdict="REDACT", redactions=[h.type for h in hits]), redact(answer, hits)
    return OutputCheck(verdict="ALLOW"), answer

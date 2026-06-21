from __future__ import annotations
import re
from vsentinel.guard_client import classify
from vsentinel.normalize import fold_diacritics
from vsentinel.pii import detect_pii, redact
from vsentinel.schema import OutputCheck

_BLOCKED_MSG = "Phản hồi đã bị chặn do vi phạm chính sách an toàn."

# High-precision markers that a generated answer is leaking the system prompt /
# its own instructions. Matched against diacritic-folded, lowercased text. Kept
# narrow so benign answers that merely mention "system" (e.g. "hệ thống y tế")
# are not blocked.
_LEAK_PATTERNS = [
    re.compile(p)
    for p in (
        r"(he thong|system).{0,12}(prompt|instruction|cau lenh)",
        r"my (system )?(instruction|prompt)s? (are|is)",
        r"toi duoc (huong dan|chi dinh) (la|rang)",
        r"ban la tro ly dich vu cong",
    )
]


def _leaks_system_prompt(answer: str) -> bool:
    folded = fold_diacritics(answer)
    return any(p.search(folded) for p in _LEAK_PATTERNS)


def check_output(answer: str, classifier=None) -> tuple[OutputCheck, str]:
    clf = classifier or classify
    if clf(answer, role="assistant") == "unsafe":
        return OutputCheck(verdict="BLOCK"), _BLOCKED_MSG
    if _leaks_system_prompt(answer):
        return OutputCheck(verdict="BLOCK"), _BLOCKED_MSG
    hits = detect_pii(answer)
    if hits:
        return OutputCheck(verdict="REDACT", redactions=[h.type for h in hits]), redact(answer, hits)
    return OutputCheck(verdict="ALLOW"), answer

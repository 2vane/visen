"""Lightweight domain routing for V-Sentinel.

Maps a user turn to one of the project's target domains — public services
(dịch vụ công), education, healthcare — so the policy layer can attach the
*right* legal framework (FERPA/COPPA for education, GDPR/PDPD for health,
ND-142/PDPD for public services) instead of a one-size-fits-all citation.

Matching is keyword-based over the diacritic-folded text (so "tiểu đường" and
"tieu duong" both hit), with word boundaries to avoid spurious substring hits.
Cheap and deterministic — no model call.
"""
from __future__ import annotations

import re

from vsentinel.normalize import fold_diacritics

# Folded (no-diacritic, lowercase) keywords per domain. Keep high-precision.
_DOMAIN_TERMS: dict[str, list[str]] = {
    "healthcare": [
        "benh", "benh vien", "benh nhan", "thuoc", "don thuoc", "bac si",
        "kham", "kham benh", "suc khoe", "y te", "tieu duong", "huyet ap",
        "ung thu", "trieu chung", "dieu tri", "vaccine", "tiem chung", "bhyt",
        "dich benh", "cap cuu",
    ],
    "education": [
        "hoc", "hoc sinh", "hoc ba", "hoc phi", "diem", "diem thi", "thi",
        "giao vien", "giao duc", "truong hoc", "phu huynh", "lop", "sinh vien",
        "bai tap", "tuyen sinh", "diem so",
    ],
    "public_service": [
        "can cuoc", "cccd", "ho chieu", "khai sinh", "ho khau", "thu tuc",
        "giay to", "dich vu cong", "bao hiem xa hoi", "bhxh", "dang ky",
        "ho tich", "cong chung", "tam tru", "thuong tru", "ket hon",
    ],
}

# Longest term first so multi-word phrases ("benh vien") win over their own
# prefix ("benh") in the regex alternation instead of being shadowed by it.
_DOMAIN_RX = {
    domain: re.compile(
        r"\b(?:" + "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + r")\b"
    )
    for domain, terms in _DOMAIN_TERMS.items()
}


def detect_domain(text: str) -> str:
    """Return the best-matching domain, or ``"general"`` if none clearly wins."""
    folded = fold_diacritics(text)
    best, best_hits = "general", 0
    for domain, rx in _DOMAIN_RX.items():
        hits = len(rx.findall(folded))
        if hits > best_hits:
            best, best_hits = domain, hits
    return best

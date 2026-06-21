"""Pure text helpers for the Neo4j retriever.

Stdlib/regex only — safe to import even when the heavy retrieval extras
(``neo4j``, ``torch``, ``sentence-transformers``) are not installed.
"""
from __future__ import annotations

import re
from typing import Any

from vsentinel.normalize import fold_diacritics

# Vietnamese-specific letters; their presence is a strong signal of Vietnamese.
VIETNAMESE_DIACRITICS = set(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệ"
    "íìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    "ĂÂĐÊÔƠƯÁÀẢÃẠẤẦẨẪẬẮẰẲẴẶÉÈẺẼẸẾỀỂỄỆ"
    "ÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ"
)

# Common unaccented Vietnamese function words, for queries typed without marks.
VIETNAMESE_HINTS = {
    "khi", "nào", "cần", "phải", "được", "không", "trẻ", "phụ", "huynh",
    "học", "sinh", "trường", "dữ", "liệu", "thu", "thập", "quyền", "nhà",
    "cung", "cấp", "hệ", "thống", "trí", "tuệ", "nhân", "tạo", "tiết", "lộ",
}


def clean_text(value: Any) -> str:
    """Collapse whitespace and non-breaking spaces into a single clean line."""
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


# Hints folded once so diacritic-less Vietnamese ("tai lieu") still matches the
# accented vocabulary above.
_FOLDED_HINTS = {fold_diacritics(h) for h in VIETNAMESE_HINTS}


def detect_query_language(text: str) -> str:
    """Distinguish Vietnamese from English well enough to drive dual-query."""
    if any(character in VIETNAMESE_DIACRITICS for character in text):
        return "vi"

    # Fold input words too, so unaccented Vietnamese is matched against hints.
    words = {fold_diacritics(w) for w in re.findall(r"[A-Za-zÀ-ỹ]+", text)}
    vietnamese_hits = len(words & _FOLDED_HINTS)
    return "vi" if vietnamese_hits >= 2 else "en"

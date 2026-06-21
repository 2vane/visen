from __future__ import annotations

import re
import unicodedata

ZERO_WIDTH = ["​", "‌", "‍", "﻿"]
LEET = {"4": "a", "3": "e", "0": "o", "1": "i", "$": "s", "@": "a", "5": "s", "7": "t"}
_COMBINING = re.compile(r"[̀-ͯ]")


def fold_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    stripped = _COMBINING.sub("", decomposed)
    return unicodedata.normalize("NFC", stripped).replace("đ", "d").replace("Đ", "D").lower()


def _has_leet_obfuscation(text: str) -> bool:
    """True when a leet char plausibly substitutes a letter *inside* a word
    (``h4ck``, ``p4ssw0rd``, ``ign0re``) — i.e. flanked by letters on both sides.

    Legitimate numerics are NOT flagged: a measurement/date/ordinal keeps its
    digits at the number↔letter boundary (``70kg``, ``5km``, ``mp3``, ``covid19``),
    never between two letters. We only flag here; we never rewrite the text —
    decoding leet for detection happens in ``detect.score_rules`` so a spurious
    decode can't corrupt the canonical text (``70kg`` → ``tokg``).
    """
    for i in range(1, len(text) - 1):
        if text[i] in LEET and text[i - 1].isalpha() and text[i + 1].isalpha():
            return True
    return False


def normalize(text: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    work = unicodedata.normalize("NFKC", text)

    if any(z in work for z in ZERO_WIDTH):
        flags.append("zero_width")
        for z in ZERO_WIDTH:
            work = work.replace(z, "")

    if re.search(r"(?:\b\w (?=\w\b))+\w\b", work) or re.search(r"\b\w(?: \w){2,}\b", work):
        flags.append("excess_spacing")
        work = re.sub(r"\b\w(?: \w)+\b", lambda m: m.group(0).replace(" ", ""), work)

    # Flag in-word leet substitution, but DO NOT rewrite the text: doing so
    # corrupts legitimate numerics (70kg -> tokg). Decoding for detection lives
    # in detect.score_rules, where a spurious decode can't leak into retrieval
    # or the user-visible normalized text.
    if _has_leet_obfuscation(work):
        flags.append("leetspeak")

    folded = fold_diacritics(work)
    if folded != work.lower():
        flags.append("diacritic_stripped")

    work = re.sub(r"\s+", " ", folded).strip()
    return work, flags

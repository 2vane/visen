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


def _decode_leet(text: str) -> str:
    return "".join(LEET.get(ch, ch) for ch in text)


def normalize(text: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    work = unicodedata.normalize("NFKC", text)

    if any(z in work for z in ZERO_WIDTH):
        flags.append("zero_width")
        for z in ZERO_WIDTH:
            work = work.replace(z, "")

    # Detect excess spacing: 4+ single characters separated by spaces, or 2+ spaces between words
    if re.search(r"\w\s\w\s\w\s\w", work) or re.search(r"\s{2,}", work):
        flags.append("excess_spacing")
        work = re.sub(r"(?<=\w)\s+(?=\w)", lambda m: " " if len(m.group()) == 1 else "", work)
        work = re.sub(r"\b(\w)\s(?=\w\b)", r"\1", work)

    leet_decoded = _decode_leet(work)
    if leet_decoded != work and re.search(r"[a-zA-Z]", work):
        flags.append("leetspeak")
        work = leet_decoded

    folded = fold_diacritics(work)
    if folded != work.lower():
        flags.append("diacritic_stripped")

    work = re.sub(r"\s+", " ", folded).strip()
    return work, flags

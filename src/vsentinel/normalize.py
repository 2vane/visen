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
    out = []
    for tok in text.split(" "):
        if any(c.isalpha() for c in tok) and any(c in LEET for c in tok):
            out.append("".join(LEET.get(c, c) for c in tok))
        else:
            out.append(tok)
    return " ".join(out)


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

    leet_decoded = _decode_leet(work)
    if leet_decoded != work and re.search(r"[a-zA-Z]", work):
        flags.append("leetspeak")
        work = leet_decoded

    folded = fold_diacritics(work)
    if folded != work.lower():
        flags.append("diacritic_stripped")

    work = re.sub(r"\s+", " ", folded).strip()
    return work, flags

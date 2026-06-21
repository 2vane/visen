from __future__ import annotations
import re
import yaml
from vsentinel.normalize import fold_diacritics
from vsentinel.resources import policy_file
from vsentinel.schema import PiiHit

_DEFAULT = policy_file("pii_recognizers.yml")

# How many chars on each side of a match to scan for a context keyword.
_CONTEXT_WINDOW = 50


def _load() -> list[dict]:
    data = yaml.safe_load(_DEFAULT.read_text(encoding="utf-8"))
    for r in data:
        r["_rx"] = re.compile(r["pattern"])
    return data


_RECOGNIZERS = None


def _recognizers() -> list[dict]:
    global _RECOGNIZERS
    if _RECOGNIZERS is None:
        _RECOGNIZERS = _load()
    return _RECOGNIZERS


def _has_context(text: str, context: list[str], start: int, end: int) -> bool:
    """True if a context keyword appears near the match (either side).

    The window and the keywords are diacritic-folded so accent-less queries
    ("can cuoc") match accented context terms ("căn cước"), and matching is
    word-boundary anchored so "cccd" no longer fires inside "acccd"/"access".
    """
    if not context:
        return True
    before = text[max(0, start - _CONTEXT_WINDOW) : start]
    after = text[end : end + _CONTEXT_WINDOW]
    window = fold_diacritics(before + " " + after)
    for c in context:
        term = fold_diacritics(c)
        if term and re.search(r"\b" + re.escape(term) + r"\b", window):
            return True
    return False


def detect_pii(text: str) -> list[PiiHit]:
    hits: list[PiiHit] = []
    taken: list[tuple[int, int]] = []
    for r in _recognizers():
        for m in r["_rx"].finditer(text):
            span = (m.start(), m.end())
            if any(span[0] < e and s < span[1] for s, e in taken):
                continue
            if not _has_context(text, r.get("context", []), m.start(), m.end()):
                continue
            hits.append(PiiHit(type=r["entity"], span=span, action="redact"))
            taken.append(span)
    return hits


def redact(text: str, hits: list[PiiHit]) -> str:
    for h in sorted(hits, key=lambda x: x.span[0], reverse=True):
        s, e = h.span
        text = text[:s] + f"[{h.type}]" + text[e:]
    return text

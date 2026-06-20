from __future__ import annotations
import re
import yaml
from vsentinel.resources import policy_file
from vsentinel.schema import PiiHit

_DEFAULT = policy_file("pii_recognizers.yml")


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


def _has_context(text: str, context: list[str], start: int) -> bool:
    if not context:
        return True
    window = text[max(0, start - 40) : start].lower()
    return any(c.lower() in window for c in context)


def detect_pii(text: str) -> list[PiiHit]:
    hits: list[PiiHit] = []
    taken: list[tuple[int, int]] = []
    for r in _recognizers():
        for m in r["_rx"].finditer(text):
            span = (m.start(), m.end())
            if any(span[0] < e and s < span[1] for s, e in taken):
                continue
            if not _has_context(text, r.get("context", []), m.start()):
                continue
            hits.append(PiiHit(type=r["entity"], span=span, action="redact"))
            taken.append(span)
    return hits


def redact(text: str, hits: list[PiiHit]) -> str:
    for h in sorted(hits, key=lambda x: x.span[0], reverse=True):
        s, e = h.span
        text = text[:s] + f"[{h.type}]" + text[e:]
    return text

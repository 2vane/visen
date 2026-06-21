from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path

import yaml

from vsentinel.normalize import LEET, fold_diacritics
from vsentinel.resources import policy_file
from vsentinel.schema import RuleHit

_DEFAULT = policy_file("jailbreak_patterns.yml")

# Base64 hides instructions from the regex rules ("aWdub3Jl..." == "ignore...").
# Decode long base64-looking tokens and scan the plaintext too. Conservative:
# only well-formed, padded tokens that decode to printable text with letters.
_B64_RX = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


def _decode_leet(text: str) -> str:
    """Map leet chars to letters for *matching only* (1gn0r3 -> ignore).

    Safe to be aggressive here: the result is tested against attack regexes,
    never shown to the user or used for retrieval, so a spurious decode
    (70kg -> tokg) simply fails to match — it can't corrupt anything.
    """
    out = []
    for tok in text.split(" "):
        if any(c.isalpha() for c in tok) and any(c in LEET for c in tok):
            out.append("".join(LEET.get(c, c) for c in tok))
        else:
            out.append(tok)
    return " ".join(out)


def _decode_b64_payloads(text: str) -> list[str]:
    decoded: list[str] = []
    for match in _B64_RX.finditer(text):
        token = match.group(0)
        if len(token) % 4:
            continue
        try:
            raw = base64.b64decode(token, validate=True)
            plain = raw.decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        if plain.isprintable() and any(c.isalpha() for c in plain):
            decoded.append(plain)
    return decoded


def load_patterns(path: str | None = None) -> list[dict]:
    p = Path(path) if path else _DEFAULT
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    for rule in data:
        rule["_compiled"] = [re.compile(pat, re.IGNORECASE) for pat in rule["patterns"]]
    return data


_RULES = None


def _rules() -> list[dict]:
    global _RULES
    if _RULES is None:
        _RULES = load_patterns()
    return _RULES


def score_rules(text: str, flags: list[str], raw: str | None = None) -> tuple[float, list[RuleHit]]:
    # Decode base64 from the RAW message: normalize() lowercases/de-leets the
    # text upstream, which would corrupt case-sensitive base64 before we see it.
    source = raw if raw is not None else text
    targets = [fold_diacritics(text)]
    # Per-token de-leet (h4ck -> hack) and a whole-string pass (catches payloads
    # split across token boundaries, e.g. "1gn 0re"). Scan-only: a spurious
    # decode (70kg -> tokg) just fails to match — it never touches the real text.
    leet = _decode_leet(text)
    if leet != text:
        targets.append(fold_diacritics(leet))
    full_leet = "".join(LEET.get(c, c) for c in text)
    if full_leet != text:
        targets.append(fold_diacritics(full_leet))
    targets.extend(fold_diacritics(p) for p in _decode_b64_payloads(source))

    hits: list[RuleHit] = []
    score = 0.0
    for rule in _rules():
        if any(rx.search(t) for rx in rule["_compiled"] for t in targets):
            hits.append(RuleHit(id=rule["id"], owasp_tag=rule.get("owasp_tag", "")))
            score = max(score, float(rule["weight"]))
    if hits and flags:
        score = min(1.0, score + 0.1)
    return score, hits

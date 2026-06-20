from __future__ import annotations

import re
from pathlib import Path

import yaml

from vsentinel.normalize import fold_diacritics
from vsentinel.resources import policy_file
from vsentinel.schema import RuleHit

_DEFAULT = policy_file("jailbreak_patterns.yml")


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


def score_rules(text: str, flags: list[str]) -> tuple[float, list[RuleHit]]:
    folded = fold_diacritics(text)
    hits: list[RuleHit] = []
    score = 0.0
    for rule in _rules():
        if any(rx.search(folded) for rx in rule["_compiled"]):
            hits.append(RuleHit(id=rule["id"], owasp_tag=rule.get("owasp_tag", "")))
            score = max(score, float(rule["weight"]))
    if hits and flags:
        score = min(1.0, score + 0.1)
    return score, hits

from __future__ import annotations
from pathlib import Path
import yaml
from vsentinel.schema import RuleHit, PolicyInfo, Citation

_POLICY = Path(__file__).resolve().parents[2] / "config" / "policy" / "legal_policy.yml"
_TEMPLATES = Path(__file__).resolve().parents[2] / "config" / "policy" / "reframe_templates.yml"

def _load_policy() -> list[dict]:
    return yaml.safe_load(_POLICY.read_text(encoding="utf-8"))

def _load_templates() -> dict:
    return yaml.safe_load(_TEMPLATES.read_text(encoding="utf-8"))

def categorize(rule_score: float, rules: list[RuleHit], guard_severity: str) -> str:
    if rule_score >= 0.8 or guard_severity == "unsafe":
        return "attack"
    if guard_severity == "controversial":
        return "sensitive_legal"
    return "benign"

def decide(category: str, guard_severity: str, retriever) -> tuple[str, PolicyInfo, str]:
    rules = _load_policy()
    rule = next((r for r in rules if r["category"] == category), rules[-1])
    citations = [Citation(**c) for c in rule.get("citations", [])]
    for art in retriever.search(rule.get("reason", category), k=1):
        citations.append(Citation(source="ND142/2026", ref=art.ref, text=art.snippet[:80]))
    policy = PolicyInfo(reason=rule["reason"], citations=citations)
    directive = ""
    if rule["action"] == "REFRAME":
        directive = _load_templates().get(rule.get("reframe_template", ""), "").strip()
    return rule["action"], policy, directive

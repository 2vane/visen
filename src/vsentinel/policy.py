from __future__ import annotations
import yaml
from vsentinel.resources import policy_file
from vsentinel.schema import RuleHit, PolicyInfo, Citation

_POLICY = policy_file("legal_policy.yml")
_TEMPLATES = policy_file("reframe_templates.yml")

# Sources a retriever may tag on an Article; anything else falls back to the
# decree so a Citation never violates its source enum.
_ALLOWED_SOURCES = {"ND142/2026", "PDPD", "GDPR", "OWASP", "FERPA", "COPPA"}

def _load_policy() -> list[dict]:
    return yaml.safe_load(_POLICY.read_text(encoding="utf-8"))

def _load_templates() -> dict:
    return yaml.safe_load(_TEMPLATES.read_text(encoding="utf-8"))

def categorize(rule_score: float, rules: list[RuleHit], guard_severity: str, attack_threshold: float = 0.8) -> str:
    if rule_score >= attack_threshold:
        return "attack"
    if guard_severity == "unsafe":
        return "illegal"
    if guard_severity == "controversial":
        return "sensitive_legal"
    return "benign"

def decide(category: str, guard_severity: str, retriever) -> tuple[str, PolicyInfo, str]:
    rules = _load_policy()
    rule = next((r for r in rules if r["category"] == category), rules[-1])
    citations = [Citation(**c) for c in rule.get("citations", [])]
    if rule["action"] != "ALLOW":
        for art in retriever.search(rule.get("reason", category), k=1):
            src = getattr(art, "source", "") or "ND142/2026"
            if src not in _ALLOWED_SOURCES:
                src = "ND142/2026"
            citations.append(Citation(source=src, ref=art.ref, text=art.snippet[:80]))
    policy = PolicyInfo(reason=rule["reason"], citations=citations)
    directive = ""
    if rule["action"] == "REFRAME":
        directive = _load_templates().get(rule.get("reframe_template", ""), "").strip()
    return rule["action"], policy, directive

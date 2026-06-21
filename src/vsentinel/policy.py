from __future__ import annotations
import yaml
from vsentinel.resources import policy_file
from vsentinel.schema import RuleHit, PolicyInfo, Citation

_POLICY = policy_file("legal_policy.yml")
_TEMPLATES = policy_file("reframe_templates.yml")
_DOMAIN_POLICY = policy_file("domain_policy.yml")

# Sources a retriever may tag on an Article; anything else falls back to the
# decree so a Citation never violates its source enum.
_ALLOWED_SOURCES = {"ND142/2026", "PDPD", "GDPR", "OWASP", "FERPA", "COPPA", "HIPAA"}

# Categories that get domain-specific legal framing (attacks keep OWASP only).
_DOMAIN_AWARE = {"sensitive_legal", "illegal"}

# Parse each policy file once and cache — decide() runs on every request, so
# re-reading from disk per call would be wasteful under proxy load (cf. detect._rules).
_POLICY_CACHE: list[dict] | None = None
_TEMPLATES_CACHE: dict | None = None
_DOMAIN_POLICY_CACHE: dict | None = None

def _load_policy() -> list[dict]:
    global _POLICY_CACHE
    if _POLICY_CACHE is None:
        _POLICY_CACHE = yaml.safe_load(_POLICY.read_text(encoding="utf-8"))
    return _POLICY_CACHE

def _load_templates() -> dict:
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is None:
        _TEMPLATES_CACHE = yaml.safe_load(_TEMPLATES.read_text(encoding="utf-8"))
    return _TEMPLATES_CACHE

def _load_domain_policy() -> dict:
    global _DOMAIN_POLICY_CACHE
    if _DOMAIN_POLICY_CACHE is None:
        _DOMAIN_POLICY_CACHE = yaml.safe_load(_DOMAIN_POLICY.read_text(encoding="utf-8"))
    return _DOMAIN_POLICY_CACHE

def _dedupe(citations: list[Citation]) -> list[Citation]:
    """Drop duplicate (source, ref) pairs, preserving first-seen order."""
    seen: set[tuple[str, str]] = set()
    out: list[Citation] = []
    for c in citations:
        key = (c.source, c.ref)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out

def categorize(rule_score: float, rules: list[RuleHit], guard_severity: str, attack_threshold: float = 0.8) -> str:
    if rule_score >= attack_threshold:
        return "attack"
    if guard_severity == "unsafe":
        return "illegal"
    if guard_severity == "controversial":
        return "sensitive_legal"
    return "benign"

def decide(
    category: str, guard_severity: str, retriever, domain: str = "general"
) -> tuple[str, PolicyInfo, str]:
    rules = _load_policy()
    rule = next((r for r in rules if r["category"] == category), rules[-1])
    citations = [Citation(**c) for c in rule.get("citations", [])]
    # Attach the legal framework for the request's domain (FERPA/COPPA for
    # education, GDPR/PDPD for health, ND142/PDPD for public services).
    if category in _DOMAIN_AWARE:
        domain_policy = _load_domain_policy()
        for c in domain_policy.get(domain, domain_policy.get("general", [])):
            citations.append(Citation(**c))
    if rule["action"] != "ALLOW":
        for art in retriever.search(rule.get("reason", category), k=1):
            src = getattr(art, "source", "") or "ND142/2026"
            if src not in _ALLOWED_SOURCES:
                src = "ND142/2026"
            citations.append(Citation(source=src, ref=art.ref, text=art.snippet[:80]))
    citations = _dedupe(citations)
    policy = PolicyInfo(reason=rule["reason"], citations=citations)
    directive = ""
    if rule["action"] == "REFRAME":
        directive = _load_templates().get(rule.get("reframe_template", ""), "").strip()
    return rule["action"], policy, directive

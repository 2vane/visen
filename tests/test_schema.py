from vsentinel.schema import DecisionTrace, RiskInfo, RuleHit

def test_decision_trace_minimal_build():
    trace = DecisionTrace(input_raw="xin chào", input_normalized="xin chao")
    assert trace.decision == "ALLOW"          # default
    assert trace.risk.category == "benign"    # default
    assert trace.obfuscation_flags == []

def test_risk_info_accepts_rule_hits():
    r = RiskInfo(score=0.9, category="attack", guard_severity="unsafe",
                 rules_fired=[RuleHit(id="ignore_prev", owasp_tag="LLM01")])
    assert r.rules_fired[0].owasp_tag == "LLM01"

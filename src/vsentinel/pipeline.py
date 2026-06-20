from __future__ import annotations
import time
from vsentinel.normalize import normalize
from vsentinel.detect import score_rules
from vsentinel.guard_client import classify
from vsentinel.policy import categorize, decide
from vsentinel.retrieve import Retriever
from vsentinel.generate import answer
from vsentinel.verify import check_output
from vsentinel.schema import DecisionTrace, RiskInfo

_RETRIEVER = Retriever()


def run(user_text: str) -> DecisionTrace:
    t0 = time.perf_counter()
    norm, flags = normalize(user_text)
    rule_score, hits = score_rules(norm, flags)
    severity = classify(user_text, role="user")
    category = categorize(rule_score, hits, severity)
    decision, policy, directive = decide(category, severity, _RETRIEVER)

    trace = DecisionTrace(
        input_raw=user_text, input_normalized=norm, obfuscation_flags=flags,
        risk=RiskInfo(score=rule_score, category=category, guard_severity=severity, rules_fired=hits),
        decision=decision, policy=policy,
    )

    if decision == "BLOCK":
        trace.final_message = policy.reason or "Yêu cầu đã bị từ chối."
        trace.latency_ms = int((time.perf_counter() - t0) * 1000)
        return trace

    articles = _RETRIEVER.search(norm, k=2)
    trace.retrieved_articles = articles
    trace.used_reframed_prompt = decision == "REFRAME"
    reply = answer(user_text, directive, articles)
    check, final_text = check_output(reply)
    trace.output_check = check
    if check.verdict == "BLOCK":
        trace.decision = "BLOCK"
    trace.final_message = final_text
    trace.latency_ms = int((time.perf_counter() - t0) * 1000)
    return trace

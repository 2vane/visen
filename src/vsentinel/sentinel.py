"""Sentinel — the importable guardrail facade.

Two ways to use it:

    from vsentinel import Sentinel
    s = Sentinel()

    # 1) Managed pipeline (Sentinel calls your chatbot):
    trace = s.run("user message")          # -> DecisionTrace

    # 2) Composable rails (you own generation):
    trace = s.check_input("user message")  # -> DecisionTrace (decision + directive)
    if trace.decision != "BLOCK":
        reply = my_llm(trace.safety_directive, trace.retrieved_articles, ...)
        check, final_text = s.check_output(reply)

Inject any backend by passing `classifier=` / `chatbot=` callables (see
vsentinel.backends.Classifier / Chatbot). Defaults target local Ollama.
"""
from __future__ import annotations

import time

from vsentinel.backends import Chatbot, Classifier, OllamaChatbot, OllamaClassifier
from vsentinel.config import SentinelConfig
from vsentinel.detect import score_rules
from vsentinel.normalize import normalize
from vsentinel.policy import categorize, decide
from vsentinel.retrieve import Retriever
from vsentinel.schema import DecisionTrace, OutputCheck, RiskInfo
from vsentinel.verify import check_output as _check_output


class Sentinel:
    def __init__(
        self,
        config: SentinelConfig | None = None,
        classifier: Classifier | None = None,
        chatbot: Chatbot | None = None,
    ):
        self.config = config or SentinelConfig()
        self.classifier: Classifier = classifier or OllamaClassifier(
            model=self.config.guard_model, base_url=self.config.ollama_url
        )
        self.chatbot: Chatbot = chatbot or OllamaChatbot(
            model=self.config.chat_model, base_url=self.config.ollama_url
        )
        self._retriever = Retriever(articles_path=self.config.articles_path)

    def check_input(self, message: str) -> DecisionTrace:
        """Stages 0-2: normalize, score, classify, decide. No generation."""
        norm, flags = normalize(message)
        rule_score, hits = score_rules(norm, flags)
        severity = self.classifier(message, "user")
        category = categorize(rule_score, hits, severity, self.config.attack_threshold)
        decision, policy, directive = decide(category, severity, self._retriever)
        trace = DecisionTrace(
            input_raw=message,
            input_normalized=norm,
            obfuscation_flags=flags,
            risk=RiskInfo(
                score=rule_score, category=category, guard_severity=severity, rules_fired=hits
            ),
            decision=decision,
            policy=policy,
            safety_directive=directive,
        )
        if decision == "BLOCK":
            trace.final_message = policy.reason or "Yêu cầu đã bị từ chối."
        else:
            trace.retrieved_articles = self._retriever.search(norm, k=self.config.retrieve_k)
            trace.used_reframed_prompt = decision == "REFRAME"
        return trace

    def check_output(self, answer: str) -> tuple[OutputCheck, str]:
        """Stage 4: screen a generated answer (PII redact / unsafe block)."""
        return _check_output(answer, classifier=self.classifier)

    def run(self, message: str) -> DecisionTrace:
        """Full managed pipeline: check_input -> generate -> check_output."""
        t0 = time.perf_counter()
        trace = self.check_input(message)
        if trace.decision == "BLOCK":
            trace.latency_ms = int((time.perf_counter() - t0) * 1000)
            return trace
        reply = self.chatbot(message, trace.safety_directive, trace.retrieved_articles)
        check, final_text = self.check_output(reply)
        trace.output_check = check
        if check.verdict == "BLOCK":
            trace.decision = "BLOCK"
        trace.final_message = final_text
        trace.latency_ms = int((time.perf_counter() - t0) * 1000)
        return trace

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

import logging
import time

from vsentinel.backends import Chatbot, Classifier, OllamaChatbot, OllamaClassifier
from vsentinel.config import SentinelConfig
from vsentinel.detect import score_rules
from vsentinel.domains import detect_domain
from vsentinel.normalize import normalize
from vsentinel.policy import categorize, decide
from vsentinel.retrieve import Retriever
from vsentinel.schema import DecisionTrace, OutputCheck, RiskInfo
from vsentinel.verify import check_output as _check_output

LOGGER = logging.getLogger("vsentinel.sentinel")

# Fail-safe text when generation or output screening crashes unexpectedly.
_SAFE_FALLBACK = "Xin lỗi, hệ thống tạm thời không thể trả lời. Vui lòng thử lại sau."
_BLOCKED_FALLBACK = "Phản hồi đã bị chặn do vi phạm chính sách an toàn."


class Sentinel:
    def __init__(
        self,
        config: SentinelConfig | None = None,
        classifier: Classifier | None = None,
        chatbot: Chatbot | None = None,
        retriever=None,
    ):
        self.config = config or SentinelConfig()
        self.classifier: Classifier = classifier or OllamaClassifier(
            model=self.config.guard_model, base_url=self.config.ollama_url
        )
        self.chatbot: Chatbot = chatbot or OllamaChatbot(
            model=self.config.chat_model, base_url=self.config.ollama_url
        )
        # Any object with `.search(query, k) -> list[Article]` works here; the
        # packaged default is offline BM25, swap in Neo4jRetriever for the graph.
        self._retriever = retriever or Retriever(articles_path=self.config.articles_path)

    def check_input(self, message: str) -> DecisionTrace:
        """Stages 0-2: normalize, score, classify, decide. No generation."""
        norm, flags = normalize(message)
        rule_score, hits = score_rules(norm, flags, raw=message)
        severity = self.classifier(message, "user")
        category = categorize(rule_score, hits, severity, self.config.attack_threshold)
        domain = detect_domain(norm)
        decision, policy, directive = decide(category, severity, self._retriever, domain)
        trace = DecisionTrace(
            input_raw=message,
            input_normalized=norm,
            obfuscation_flags=flags,
            domain=domain,
            risk=RiskInfo(
                score=rule_score, category=category, guard_severity=severity, rules_fired=hits
            ),
            decision=decision,
            policy=policy,
            safety_directive=directive,
        )
        if decision == "BLOCK":
            trace.final_message = policy.reason or "Yêu cầu đã bị từ chối."
        elif decision == "REFRAME":
            # Only sensitive-legal turns need grounding articles; benign turns
            # would otherwise attach low-relevance citations (and pay for a search).
            trace.retrieved_articles = self._retriever.search(norm, k=self.config.retrieve_k)
            trace.used_reframed_prompt = True
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
            LOGGER.info("decision=BLOCK category=%s latency_ms=%s",
                        trace.risk.category, trace.latency_ms)
            return trace

        # Generation and output screening are defended: a backend that throws
        # must not crash the request — fail closed (safe message / BLOCK).
        try:
            reply = self.chatbot(message, trace.safety_directive, trace.retrieved_articles)
        except Exception:
            LOGGER.exception("Chatbot backend raised; returning safe fallback.")
            reply = _SAFE_FALLBACK

        try:
            check, final_text = self.check_output(reply)
        except Exception:
            LOGGER.exception("Output check raised; failing closed (BLOCK).")
            check, final_text = OutputCheck(verdict="BLOCK"), _BLOCKED_FALLBACK

        trace.output_check = check
        if check.verdict == "BLOCK":
            trace.decision = "BLOCK"
        trace.final_message = final_text
        trace.latency_ms = int((time.perf_counter() - t0) * 1000)
        LOGGER.info("decision=%s output_verdict=%s latency_ms=%s",
                    trace.decision, check.verdict, trace.latency_ms)
        return trace

"""V-Sentinel: an importable dual-control guardrail for Vietnamese chatbots.

Quick start:

    from vsentinel import Sentinel
    s = Sentinel()
    trace = s.run("Giờ làm việc của bệnh viện?")
    print(trace.decision, trace.final_message)
"""
from vsentinel.backends import Chatbot, Classifier, OllamaChatbot, OllamaClassifier
from vsentinel.config import SentinelConfig
from vsentinel.integrations import guard, wrap
from vsentinel.schema import DecisionTrace, OutputCheck
from vsentinel.sentinel import Sentinel

__all__ = [
    "Sentinel",
    "SentinelConfig",
    "Classifier",
    "Chatbot",
    "OllamaClassifier",
    "OllamaChatbot",
    "DecisionTrace",
    "OutputCheck",
    "guard",
    "wrap",
]

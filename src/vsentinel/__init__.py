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
    "Neo4jRetriever",
    "Neo4jConfig",
]


def __getattr__(name: str):
    """Lazily expose the optional Neo4j backend.

    Kept out of the eager imports so ``import vsentinel`` never requires the
    heavy ``[neo4j]`` extra (torch / sentence-transformers / neo4j driver).
    """
    if name in ("Neo4jRetriever", "Neo4jConfig"):
        from vsentinel import retrievers

        return getattr(retrievers, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

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
    "create_app",
    "VSentinelClient",
    "Neo4jRetriever",
    "Neo4jConfig",
    "FallbackRetriever",
]


def __getattr__(name: str):
    """Lazily expose optional surfaces so plain ``import vsentinel`` stays light.

    - Neo4j backend: avoids requiring the heavy ``[neo4j]`` extra.
    - server/client: avoids importing FastAPI/httpx unless actually used.
    """
    if name in ("Neo4jRetriever", "Neo4jConfig", "FallbackRetriever"):
        from vsentinel import retrievers

        return getattr(retrievers, name)
    if name == "create_app":
        from vsentinel.server import create_app

        return create_app
    if name == "VSentinelClient":
        from vsentinel.client import VSentinelClient

        return VSentinelClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

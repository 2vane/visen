"""Optional retrieval backends for V-Sentinel.

Importing this package is cheap — it does NOT pull in ``neo4j``/``torch``.
Those load lazily only when a ``Neo4jRetriever`` actually runs a search.
"""
from vsentinel.retrievers.fallback import FallbackRetriever
from vsentinel.retrievers.hybrid import HybridRetriever
from vsentinel.retrievers.neo4j_config import Neo4jConfig
from vsentinel.retrievers.neo4j_retriever import Neo4jRetriever

__all__ = ["Neo4jRetriever", "Neo4jConfig", "FallbackRetriever", "HybridRetriever"]

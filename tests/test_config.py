import pytest

from vsentinel.config import SentinelConfig
from vsentinel.retrievers.neo4j_config import Neo4jConfig


def test_sentinel_defaults_valid():
    cfg = SentinelConfig()
    assert 0.0 <= cfg.attack_threshold <= 1.0
    assert cfg.retrieve_k >= 1


@pytest.mark.parametrize("kwargs", [
    {"attack_threshold": 1.5},
    {"attack_threshold": -0.1},
    {"retrieve_k": 0},
    {"ollama_url": "ftp://nope"},
])
def test_sentinel_invalid_raises(kwargs):
    with pytest.raises(ValueError):
        SentinelConfig(**kwargs)


def test_neo4j_defaults_valid():
    Neo4jConfig()  # should not raise


@pytest.mark.parametrize("kwargs", [
    {"candidate_k": 0},
    {"min_score": -0.5},
    {"rrf_k": 0},
    {"expected_dimension": 0},
])
def test_neo4j_invalid_raises(kwargs):
    with pytest.raises(ValueError):
        Neo4jConfig(**kwargs)

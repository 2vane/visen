"""Offline tests for the Neo4j retriever — every heavy dep is mocked.

These must pass without ``neo4j``/``torch``/``sentence-transformers`` installed,
so we inject fake embedder/driver collaborators and disable rerank + dual-query.
"""
from __future__ import annotations

import pytest

from vsentinel.retrievers import Neo4jConfig, Neo4jRetriever
from vsentinel.retrievers.fusion import fuse_hits, rerank_rows, select_corpora
from vsentinel.schema import Article


# --- Neo4jConfig.from_env ----------------------------------------------------

def test_from_env_reads_vars(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://example.databases.neo4j.io")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("NEO4J_DATABASE", "mydb")

    config = Neo4jConfig.from_env()

    assert config.uri == "neo4j+s://example.databases.neo4j.io"
    assert config.username == "neo4j"
    assert config.password == "secret"
    assert config.database == "mydb"


def test_from_env_database_defaults_to_neo4j(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://example.databases.neo4j.io")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.delenv("NEO4J_DATABASE", raising=False)

    assert Neo4jConfig.from_env().database == "neo4j"


def test_from_env_missing_required_raises(monkeypatch):
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    with pytest.raises(ValueError, match="NEO4J_URI"):
        Neo4jConfig.from_env()


# --- fake collaborators ------------------------------------------------------

class _FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        return [0.0] * 1024


def _canned_row(node_id: str, citation: str, text: str, score: float, rank: int) -> dict:
    return {
        "id": node_id,
        "citation": citation,
        "kind": "clause",
        "text": text,
        "context_text": "",
        "section_number": None,
        "section_title": None,
        "article_number": "15",
        "clause_number": "1",
        "point_label": None,
        "paragraph_path": None,
        "term": None,
        "score": score,
        "corpus": "vn",
        "index_name": "legal_embedding_index",
        "document_id": "142-2026-nd-cp",
        "document_citation": "Nghị định 142/2026/NĐ-CP",
        "corpus_name": "Vietnam AI Decree",
        "query_variant": "original",
        "query_text": "q",
        "query_language": "vi",
        "query_rank": rank,
    }


class _FakeDriver:
    def online_vector_indexes(self) -> dict[str, str]:
        return {"legal_embedding_index": "ONLINE"}

    def vector_search(self, **kwargs) -> list[dict]:
        return [
            _canned_row(
                "142-2026-nd-cp:unit:001",
                "Khoản 1 Điều 15 142/2026/NĐ-CP",
                "Nhà cung cấp hệ thống AI rủi ro cao phải quản lý rủi ro.",
                0.91,
                1,
            ),
            _canned_row(
                "142-2026-nd-cp:unit:002",
                "Khoản 2 Điều 15 142/2026/NĐ-CP",
                "Bên triển khai phải đánh giá sự phù hợp định kỳ.",
                0.83,
                2,
            ),
            _canned_row(
                "142-2026-nd-cp:unit:003",
                "Điều 16 142/2026/NĐ-CP",
                "Trách nhiệm minh bạch với người dùng.",
                0.70,
                3,
            ),
        ]

    def expand_context(self, **kwargs) -> list[dict]:
        return []

    def connect(self) -> None:  # pragma: no cover - trivial
        pass

    def close(self) -> None:  # pragma: no cover - trivial
        pass


# --- Neo4jRetriever.search end-to-end (mocked) -------------------------------

def test_search_returns_articles_from_canned_rows():
    config = Neo4jConfig(
        uri="x", username="u", password="p",
        dual_query=False, rerank=False, law="vn",
    )
    retriever = Neo4jRetriever(
        config=config,
        embedder=_FakeEmbedder(),
        driver=_FakeDriver(),
    )
    # Driver is injected, so mark it connected to skip real connectivity.
    retriever._connected = True

    articles = retriever.search("Trách nhiệm của nhà cung cấp hệ thống AI?", k=2)

    assert isinstance(articles, list)
    assert len(articles) == 2
    assert all(isinstance(a, Article) for a in articles)
    # Top hit (highest fusion/vector score) should be Khoản 1 Điều 15.
    assert articles[0].ref == "Khoản 1 Điều 15 142/2026/NĐ-CP"
    assert "rủi ro" in articles[0].snippet
    assert articles[1].ref == "Khoản 2 Điều 15 142/2026/NĐ-CP"
    # Source is tagged from the corpus so policy citations attribute the right law.
    assert articles[0].source == "ND142/2026"


def test_search_tags_coppa_source():
    """A COPPA-corpus hit is tagged source='COPPA', not the default decree."""
    class _CoppaDriver(_FakeDriver):
        def online_vector_indexes(self):
            return {"coppa_embedding_index": "ONLINE"}

        def vector_search(self, **kwargs):
            row = _canned_row("coppa:001", "16 CFR § 312.5", "Verifiable parental consent.", 0.9, 1)
            row.update(corpus="coppa", index_name="coppa_embedding_index",
                       document_id="us-coppa-16-cfr-part-312")
            return [row]

    config = Neo4jConfig(uri="x", username="u", password="p",
                         dual_query=False, rerank=False, law="coppa")
    retriever = Neo4jRetriever(config=config, embedder=_FakeEmbedder(), driver=_CoppaDriver())
    retriever._connected = True

    articles = retriever.search("verifiable parental consent under 13", k=1)
    assert articles[0].source == "COPPA"


def test_search_recovers_after_reconnect():
    """A transient driver failure triggers one reconnect + retry, then succeeds."""

    class _FlakyDriver(_FakeDriver):
        def __init__(self):
            self.connect_calls = 0
            self.search_calls = 0

        def connect(self):
            self.connect_calls += 1

        def vector_search(self, **kwargs):
            self.search_calls += 1
            if self.search_calls == 1:
                raise RuntimeError("connection reset by peer")
            return super().vector_search(**kwargs)

    config = Neo4jConfig(uri="x", username="u", password="p",
                         dual_query=False, rerank=False, law="vn")
    driver = _FlakyDriver()
    retriever = Neo4jRetriever(config=config, embedder=_FakeEmbedder(), driver=driver)
    retriever._connected = True  # already connected, so a failure reconnects

    articles = retriever.search("Trách nhiệm của nhà cung cấp?", k=1)

    assert articles  # recovered with real results
    assert driver.connect_calls == 1  # reconnected exactly once
    assert driver.search_calls == 2   # failed once, retried once


def test_reconnect_rebuilds_internally_owned_driver(monkeypatch):
    """An owned (non-injected) driver is closed AND rebuilt on reconnect.

    Regression test: a real Neo4j driver raises if connect()/verify_connectivity
    is called after close(), so _reconnect must null the old driver so a fresh
    one is constructed — not reuse the closed object.
    """
    built = []

    class _OwnedDriver:
        def __init__(self, config):
            built.append(self)
            self.closed = False

        def connect(self):
            assert not self.closed, "connect() called on a closed driver"

        def close(self):
            self.closed = True

        def online_vector_indexes(self):
            return {"legal_embedding_index": "ONLINE"}

        def vector_search(self, **kwargs):
            if self is built[0]:
                raise RuntimeError("connection reset by peer")
            return _FakeDriver().vector_search(**kwargs)

    monkeypatch.setattr("vsentinel.retrievers.driver.Neo4jDriver", _OwnedDriver)
    config = Neo4jConfig(uri="x", username="u", password="p",
                         dual_query=False, rerank=False, law="vn")
    retriever = Neo4jRetriever(config=config, embedder=_FakeEmbedder())  # owns its driver

    articles = retriever.search("Trách nhiệm của nhà cung cấp?", k=1)

    assert articles                 # recovered after rebuild
    assert len(built) == 2          # a fresh driver was constructed on reconnect
    assert built[0].closed is True  # the stale driver was closed


def test_search_raises_when_no_index_online():
    class _OfflineDriver(_FakeDriver):
        def online_vector_indexes(self) -> dict[str, str]:
            return {"legal_embedding_index": "POPULATING"}

    config = Neo4jConfig(uri="x", username="u", password="p", dual_query=False, rerank=False, law="vn")
    retriever = Neo4jRetriever(config=config, embedder=_FakeEmbedder(), driver=_OfflineDriver())
    retriever._connected = True

    with pytest.raises(RuntimeError, match="ONLINE"):
        retriever.search("bất kỳ câu hỏi nào", k=2)


# --- pure RRF math -----------------------------------------------------------

def test_fuse_hits_accumulates_rrf_contributions():
    rrf_k = 60
    # Same node id appears for two query variants at ranks 1 and 3.
    rows = [
        {"id": "n1", "score": 0.9, "query_rank": 1, "query_variant": "original"},
        {"id": "n1", "score": 0.7, "query_rank": 3, "query_variant": "translated"},
        {"id": "n2", "score": 0.8, "query_rank": 2, "query_variant": "original"},
    ]

    fused = fuse_hits(rows, rrf_k=rrf_k)
    by_id = {row["id"]: row for row in fused}

    expected_n1 = 1.0 / (rrf_k + 1) + 1.0 / (rrf_k + 3)
    assert by_id["n1"]["fusion_score"] == pytest.approx(expected_n1)
    assert by_id["n2"]["fusion_score"] == pytest.approx(1.0 / (rrf_k + 2))
    # n1 (two contributions) outranks n2 (one) -> sorted first.
    assert fused[0]["id"] == "n1"
    # Best raw score is preserved across the merge.
    assert by_id["n1"]["score"] == pytest.approx(0.9)


# --- relevance: language-gated routing + reranker floor ----------------------

def test_auto_routing_uses_fallback_when_uncertain():
    """An uncertain query routes to the fallback corpus, not every corpus."""
    selected, _ = select_corpora("xin chào buổi sáng", "auto", fallback=["vn"])
    assert selected == ["vn"]


def test_auto_routing_without_fallback_queries_all():
    """No fallback => uncertain queries still fan out to every corpus."""
    selected, _ = select_corpora("xin chào buổi sáng", "auto")
    assert set(selected) == {"vn", "ferpa", "coppa"}


def test_explicit_keyword_still_routes_to_its_corpus():
    """A FERPA cue routes to FERPA even with a VN fallback available."""
    selected, _ = select_corpora(
        "When can a school disclose education records?", "auto", fallback=["vn"]
    )
    assert "ferpa" in selected


def test_rerank_floor_drops_offtopic_candidates():
    """min_reranker_score drops weak matches so off-topic queries cite nothing."""

    class _FakeReranker:
        # First candidate clearly relevant, second clearly off-topic.
        def score_pairs(self, pairs, normalize=True):
            return [0.95, 0.02]

    rows = [
        {"id": "a", "corpus": "vn", "citation": "Điều 15", "text": "relevant", "query_text": "q"},
        {"id": "b", "corpus": "vn", "citation": "Mẫu AI07b", "text": "a form", "query_text": "q"},
    ]
    qv = {"vn": [{"variant": "original", "language": "vi", "text": "q"}]}

    kept = rerank_rows(rows, qv, _FakeReranker(), rerank_top_n=2,
                       query_mode="both", min_reranker_score=0.3)
    assert [r["id"] for r in kept] == ["a"]


def test_from_env_device_overrides(monkeypatch):
    """Embedder/reranker device is env-tunable (CPU pin for small GPUs)."""
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://x.databases.neo4j.io")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "pw")
    monkeypatch.setenv("VSENTINEL_EMBED_DEVICE", "cpu")
    monkeypatch.setenv("VSENTINEL_RERANK_DEVICE", "cpu")
    cfg = Neo4jConfig.from_env()
    assert cfg.device == "cpu"
    assert cfg.reranker_device == "cpu"


def test_from_env_device_defaults_auto(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://x.databases.neo4j.io")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "pw")
    monkeypatch.delenv("VSENTINEL_EMBED_DEVICE", raising=False)
    cfg = Neo4jConfig.from_env()
    assert cfg.device == "auto"

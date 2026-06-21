"""Neo4j-backed legal retriever — a drop-in for the BM25 ``Retriever``.

Exposes ``search(query, k) -> list[Article]`` so it can be injected straight
into ``Sentinel(retriever=...)``. Embedding / translation / reranking / driver
collaborators are constructed lazily on first ``search`` (or injected for
tests), so importing this module never requires the ``neo4j`` extra.
"""
from __future__ import annotations

import logging
from typing import Optional

from vsentinel.retrievers.fusion import fuse_hits, rerank_rows, select_corpora
from vsentinel.retrievers.neo4j_config import CORPORA, Neo4jConfig
from vsentinel.retrievers.text_utils import clean_text, detect_query_language
from vsentinel.schema import Article

LOGGER = logging.getLogger("vsentinel.retrievers.neo4j")


class Neo4jRetriever:
    """Semantic legal retrieval over the V-Sentinel Neo4j knowledge graph."""

    def __init__(
        self,
        config: Neo4jConfig | None = None,
        *,
        embedder=None,
        driver=None,
        translator=None,
        reranker=None,
    ) -> None:
        self.config = config or Neo4jConfig.from_env()
        self._embedder = embedder
        self._driver = driver
        self._translator = translator
        self._reranker = reranker
        self._connected = False

    # -- lazy collaborator construction ------------------------------------

    def _ensure_embedder(self):
        if self._embedder is None:
            from vsentinel.retrievers.embedder import Embedder

            self._embedder = Embedder(
                self.config.embedding_model,
                self.config.device,
                self.config.expected_dimension,
            )
        return self._embedder

    def _ensure_driver(self):
        if self._driver is None:
            from vsentinel.retrievers.driver import Neo4jDriver

            self._driver = Neo4jDriver(self.config)
        if not self._connected:
            self._driver.connect()
            self._connected = True
        return self._driver

    def _ensure_translator(self):
        if self._translator is None:
            from vsentinel.retrievers.translator import LocalTranslator

            self._translator = LocalTranslator(
                self.config.translation_model,
                self.config.translation_device,
            )
        return self._translator

    def _ensure_reranker(self):
        if self._reranker is None:
            from vsentinel.retrievers.reranker import CrossEncoderReranker

            self._reranker = CrossEncoderReranker(
                model_name=self.config.reranker_model,
                device=self.config.reranker_device,
                batch_size=self.config.reranker_batch_size,
                max_length=self.config.reranker_max_length,
                use_fp16=self.config.reranker_fp16,
            )
        return self._reranker

    # -- query-variant construction ----------------------------------------

    def _build_variants(
        self,
        question: str,
        corpus: str,
        source_language: str,
    ) -> list[dict[str, str]]:
        variants: list[dict[str, str]] = [
            {"variant": "original", "language": source_language, "text": question}
        ]

        corpus_language = CORPORA[corpus]["language"]
        if self.config.dual_query and source_language != corpus_language:
            try:
                translated = self._ensure_translator().translate(
                    text=question,
                    source_language=source_language,
                    target_language=corpus_language,
                    max_new_tokens=self.config.translation_max_new_tokens,
                )
            except Exception as exc:  # translation is best-effort; fall back to original
                LOGGER.warning(
                    "Không dịch được query cho corpus %s; dùng câu gốc: %s",
                    corpus,
                    exc,
                )
                translated = ""

            if translated and translated.casefold() != question.casefold():
                variants.append(
                    {"variant": "translated", "language": corpus_language, "text": translated}
                )

        return variants

    def _reconnect(self) -> None:
        """Drop a stale connection so the next ``_ensure_driver`` reconnects."""
        self._connected = False
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception as exc:  # closing a dead driver is best-effort
                LOGGER.warning("Lỗi khi đóng driver cũ: %s", exc)
        self._ensure_driver()

    def _collect_rows(
        self, query: str, source_language: str, fallback: Optional[list[str]]
    ) -> tuple[list[dict], dict[str, list[dict[str, str]]]]:
        """Run routing + per-corpus vector search; touches the live driver."""
        driver = self._ensure_driver()
        embedder = self._ensure_embedder()

        selected, _ = select_corpora(query, self.config.law, fallback=fallback)
        indexes = driver.online_vector_indexes()
        available = [
            corpus for corpus in selected
            if indexes.get(CORPORA[corpus]["index"]) == "ONLINE"
        ]
        if not available:
            raise RuntimeError(
                "Không có vector index phù hợp ở trạng thái ONLINE trên Neo4j."
            )

        embedding_cache: dict[str, list[float]] = {}
        query_variants: dict[str, list[dict[str, str]]] = {}
        raw_rows: list[dict] = []

        def embed(text: str) -> list[float]:
            if text not in embedding_cache:
                embedding_cache[text] = embedder.embed(text)
            return embedding_cache[text]

        for corpus in available:
            variants = self._build_variants(query, corpus, source_language)
            query_variants[corpus] = variants
            for variant in variants:
                raw_rows.extend(
                    driver.vector_search(
                        corpus=corpus,
                        embedding=embed(variant["text"]),
                        candidate_k=self.config.candidate_k,
                        min_score=self.config.min_score,
                        query_variant=variant["variant"],
                        query_text=variant["text"],
                        query_language=variant["language"],
                    )
                )

        return raw_rows, query_variants

    # -- public API ---------------------------------------------------------

    def search(self, query: str, k: int = 2) -> list[Article]:
        """Retrieve the top-``k`` legal units as :class:`Article` citations."""
        source_language = detect_query_language(query)
        # Uncertain auto-routing falls back to the default corpus only when the
        # query is in that corpus's language (keeps US law out of VN queries).
        fallback = None
        dc = self.config.default_corpus
        if dc and dc in CORPORA and CORPORA[dc]["language"] == source_language:
            fallback = [dc]

        try:
            raw_rows, query_variants = self._collect_rows(query, source_language, fallback)
        except Exception as exc:
            # A dropped/stale Neo4j connection recovers with one reconnect+retry;
            # a persistent failure re-raises (a FallbackRetriever can catch it).
            if self._driver is None or not self._connected:
                raise
            LOGGER.warning("Neo4j query lỗi (%s); kết nối lại và thử lại một lần.", exc)
            self._reconnect()
            raw_rows, query_variants = self._collect_rows(query, source_language, fallback)

        ranked = fuse_hits(raw_rows, rrf_k=self.config.rrf_k)

        if self.config.rerank and ranked:
            try:
                ranked = rerank_rows(
                    rows=ranked,
                    query_variants=query_variants,
                    reranker=self._ensure_reranker(),
                    rerank_top_n=min(self.config.rerank_top_n, len(ranked)),
                    query_mode=self.config.rerank_query_mode,
                    min_reranker_score=self.config.min_reranker_score,
                )
            except Exception as exc:
                if self.config.require_reranker:
                    raise
                LOGGER.warning("Reranker lỗi; fallback về RRF: %s", exc)

        return [self._to_article(row) for row in ranked[:k]]

    # Maps the internal corpus key to the Citation.source label so downstream
    # policy citations are attributed to the right law, not a hardcoded decree.
    _CORPUS_SOURCE = {"vn": "ND142/2026", "ferpa": "FERPA", "coppa": "COPPA"}

    def _to_article(self, row: dict) -> Article:
        ref = clean_text(row.get("citation")) or clean_text(row.get("document_citation"))
        source = self._CORPUS_SOURCE.get(row.get("corpus"), "")
        return Article(ref=ref, snippet=clean_text(row.get("text")), source=source)

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        if self._driver is not None and self._connected:
            self._driver.close()
            self._connected = False

    def __enter__(self) -> "Neo4jRetriever":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

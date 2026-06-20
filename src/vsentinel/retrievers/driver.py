"""Neo4j connection + Cypher for vector search and context expansion.

The ``neo4j`` driver is imported lazily so the package imports without the
``neo4j`` extra installed.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from vsentinel.retrievers.neo4j_config import CORPORA, Neo4jConfig

LOGGER = logging.getLogger("vsentinel.retrievers.driver")


class Neo4jDriver:
    """Thin wrapper over the Neo4j Python driver for legal-unit retrieval."""

    def __init__(self, config: Neo4jConfig, corpora: dict = CORPORA) -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError(
                "Neo4jRetriever cần gói neo4j. Cài extra: "
                "pip install 'vsentinel[neo4j]'"
            ) from exc

        if not (config.uri and config.username and config.password):
            raise ValueError(
                "Neo4jConfig thiếu uri/username/password. "
                "Dùng Neo4jConfig.from_env() hoặc truyền tường minh."
            )

        self._corpora = corpora
        self.driver = GraphDatabase.driver(
            config.uri,
            auth=(config.username, config.password),
        )
        self.database = config.database or "neo4j"

    def close(self) -> None:
        self.driver.close()

    def connect(self) -> None:
        self.driver.verify_connectivity()

        candidates = list(dict.fromkeys([self.database, "neo4j"]))
        last_error: Optional[Exception] = None

        for database in candidates:
            try:
                records, _, _ = self.driver.execute_query(
                    "RETURN 1 AS ok",
                    database_=database,
                )
                if records and records[0]["ok"] == 1:
                    self.database = database
                    LOGGER.info("Đã kết nối Neo4j; database=%s", database)
                    return
            except Exception as exc:
                last_error = exc

        if last_error:
            raise last_error
        raise RuntimeError("Không xác định được database Neo4j.")

    def online_vector_indexes(self) -> dict[str, str]:
        records, _, _ = self.driver.execute_query(
            """
            SHOW VECTOR INDEXES
            YIELD name, state
            RETURN name, state
            """,
            database_=self.database,
        )
        return {
            str(record["name"]): str(record["state"])
            for record in records
        }

    def vector_search(
        self,
        corpus: str,
        embedding: list[float],
        candidate_k: int,
        min_score: float,
        query_variant: str,
        query_text: str,
        query_language: str,
    ) -> list[dict[str, Any]]:
        config = self._corpora[corpus]
        index_name = config["index"]

        # Index name comes from internal config, never directly from user input.
        query = f"""
        CALL db.index.vector.queryNodes(
            '{index_name}',
            $candidate_k,
            $embedding
        )
        YIELD node, score
        WHERE node.document_id = $document_id
          AND score >= $min_score
        RETURN
            node.id AS id,
            node.citation AS citation,
            node.kind AS kind,
            node.text AS text,
            node.context_text AS context_text,
            node.section_number AS section_number,
            node.section_title AS section_title,
            node.article_number AS article_number,
            node.clause_number AS clause_number,
            node.point_label AS point_label,
            node.paragraph_path AS paragraph_path,
            node.term AS term,
            score
        ORDER BY score DESC
        LIMIT $candidate_k
        """

        records, _, _ = self.driver.execute_query(
            query,
            candidate_k=candidate_k,
            embedding=embedding,
            document_id=config["document_id"],
            min_score=min_score,
            database_=self.database,
        )

        rows = []
        for rank, record in enumerate(records, start=1):
            row = record.data()
            row["corpus"] = corpus
            row["index_name"] = index_name
            row["document_id"] = config["document_id"]
            row["document_citation"] = config["citation"]
            row["corpus_name"] = config["name"]
            row["query_variant"] = query_variant
            row["query_text"] = query_text
            row["query_language"] = query_language
            row["query_rank"] = rank
            rows.append(row)

        return rows

    def expand_context(
        self,
        document_id: str,
        node_id: str,
        neighbors: int,
    ) -> list[dict[str, Any]]:
        if neighbors <= 0:
            return []

        records, _, _ = self.driver.execute_query(
            """
            MATCH (target:LegalUnit {id: $node_id, document_id: $document_id})
            MATCH (context:LegalUnit {document_id: $document_id})
            WHERE context.order >= target.order - $neighbors
              AND context.order <= target.order + $neighbors
              AND (
                    (
                        coalesce(target.section_id, '') <> ''
                        AND context.section_id = target.section_id
                    )
                    OR (
                        coalesce(target.section_id, '') = ''
                        AND coalesce(target.article_number, '') <> ''
                        AND context.article_number = target.article_number
                    )
                    OR (
                        coalesce(target.section_id, '') = ''
                        AND coalesce(target.article_number, '') = ''
                        AND coalesce(target.appendix_id, '') <> ''
                        AND context.appendix_id = target.appendix_id
                    )
                  )
            RETURN
                context.id AS id,
                context.order AS order,
                context.citation AS citation,
                context.kind AS kind,
                context.text AS text,
                context.id = target.id AS is_target
            ORDER BY context.order
            """,
            node_id=node_id,
            document_id=document_id,
            neighbors=neighbors,
            database_=self.database,
        )

        return [record.data() for record in records]

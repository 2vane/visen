"""Configuration + corpus tables for the Neo4j legal-knowledge retriever.

Stdlib only — importing this module never pulls in ``neo4j`` or ``torch``.
Credentials are read from the environment (``from_env``) or passed explicitly;
they are never hardcoded here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

# Maps internal language codes to NLLB language tokens for dual-query translation.
LANGUAGE_CODES = {
    "vi": "vie_Latn",
    "en": "eng_Latn",
}

# One entry per legal corpus. ``index`` and ``document_id`` come from here (not
# user input), so the Cypher that interpolates the index name stays safe.
CORPORA: dict[str, dict[str, str]] = {
    "vn": {
        "name": "Vietnam AI Decree",
        "short_name": "VN-AI",
        "index": "legal_embedding_index",
        "document_id": "142-2026-nd-cp",
        "citation": "Nghị định 142/2026/NĐ-CP",
        "jurisdiction": "VN",
        "language": "vi",
    },
    "ferpa": {
        "name": "Family Educational Rights and Privacy Act regulations",
        "short_name": "FERPA",
        "index": "ferpa_embedding_index",
        "document_id": "us-ferpa-34-cfr-part-99",
        "citation": "34 CFR Part 99",
        "jurisdiction": "US-FEDERAL",
        "language": "en",
    },
    "coppa": {
        "name": "Children's Online Privacy Protection Rule",
        "short_name": "COPPA",
        "index": "coppa_embedding_index",
        "document_id": "us-coppa-16-cfr-part-312",
        "citation": "16 CFR Part 312",
        "jurisdiction": "US-FEDERAL",
        "language": "en",
    },
}

# Keyword cues that route a free-text question to the most relevant corpus.
ROUTER_TERMS: dict[str, tuple[str, ...]] = {
    "vn": (
        "nghị định 142",
        "142/2026",
        "trí tuệ nhân tạo",
        "hệ thống ai",
        "ai rủi ro cao",
        "nhà cung cấp hệ thống",
        "bên triển khai",
        "quản lý rủi ro",
        "đánh giá sự phù hợp",
        "việt nam",
    ),
    "ferpa": (
        "ferpa",
        "34 cfr part 99",
        "34 cfr 99",
        "education record",
        "education records",
        "educational agency",
        "educational institution",
        "eligible student",
        "directory information",
        "school official",
        "student record",
        "student records",
        "hồ sơ giáo dục",
        "hồ sơ học sinh",
        "trường học",
        "sinh viên",
        "học sinh",
    ),
    "coppa": (
        "coppa",
        "16 cfr part 312",
        "16 cfr 312",
        "under 13",
        "child under 13",
        "children under 13",
        "verifiable parental consent",
        "parental consent",
        "website directed to children",
        "online service directed to children",
        "operator",
        "persistent identifier",
        "trẻ dưới 13",
        "trẻ em dưới 13",
        "đồng ý của phụ huynh",
        "dịch vụ trực tuyến cho trẻ em",
        "website dành cho trẻ em",
        "trẻ em",
        "11 tuổi",
        "12 tuổi",
        "vị trí",
        "định vị",
        "geolocation",
        "location data",
        "personal information",
        "ứng dụng học tập",
        "educational app",
    ),
}

_REQUIRED_ENV = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD")


@dataclass
class Neo4jConfig:
    """Connection + retrieval tunables for :class:`Neo4jRetriever`.

    Credentials must be supplied via :meth:`from_env` or explicit arguments;
    there are intentionally no credential defaults.
    """

    # Connection (no hardcoded credentials — populate via from_env / explicit args).
    uri: str = ""
    username: str = ""
    password: str = field(default="", repr=False)
    database: str = "neo4j"

    # Embedding model — must match the model used to build the corpus.
    embedding_model: str = "BAAI/bge-m3"
    expected_dimension: int = 1024
    device: str = "auto"

    # Dual-query translation (query original + translated when languages differ).
    dual_query: bool = True
    translation_model: str = "facebook/nllb-200-distilled-600M"
    translation_device: str = "auto"
    translation_max_new_tokens: int = 192

    # Cross-encoder reranking of fused candidates.
    rerank: bool = True
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_device: str = "auto"
    reranker_batch_size: int = 8
    reranker_max_length: int = 512
    reranker_fp16: bool = True
    rerank_top_n: int = 50
    rerank_query_mode: str = "both"
    min_reranker_score: float = 0.0
    require_reranker: bool = False

    # Routing + vector search.
    law: str = "auto"
    candidate_k: int = 20
    min_score: float = 0.0
    neighbors: int = 1
    rrf_k: int = 60

    @classmethod
    def from_env(cls, **overrides) -> "Neo4jConfig":
        """Build a config from ``NEO4J_*`` env vars; ``overrides`` win over them.

        Raises ``ValueError`` listing every missing required credential so the
        failure is actionable rather than a late connection error.
        """
        missing = [name for name in _REQUIRED_ENV if not os.environ.get(name)]
        if missing:
            raise ValueError(
                "Thiếu biến môi trường Neo4j: "
                + ", ".join(missing)
                + ". Hãy đặt chúng (ví dụ trong file .env) trước khi dùng Neo4jRetriever."
            )

        env_values = {
            "uri": os.environ["NEO4J_URI"],
            "username": os.environ["NEO4J_USERNAME"],
            "password": os.environ["NEO4J_PASSWORD"],
            "database": os.environ.get("NEO4J_DATABASE", "neo4j") or "neo4j",
        }
        env_values.update(overrides)
        return cls(**env_values)

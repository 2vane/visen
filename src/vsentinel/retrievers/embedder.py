"""Lazy bge-m3 sentence embedder for query encoding.

``sentence_transformers`` / ``torch`` are imported only on first use so the
package imports without the ``neo4j`` extra.
"""
from __future__ import annotations

import logging
from typing import Any

from vsentinel.retrievers.devices import resolve_device

LOGGER = logging.getLogger("vsentinel.retrievers.embedder")


class Embedder:
    """Encodes queries with the same model used to build the corpus.

    The corpus and query MUST share the embedding model and dimension, so the
    dimension is verified on load and again per query.
    """

    def __init__(self, model_name: str, device: str, expected_dimension: int) -> None:
        self.model_name = model_name
        self.requested_device = device
        self.expected_dimension = expected_dimension
        self._model: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Embedding cần sentence-transformers. Cài extra: "
                "pip install 'vsentinel[neo4j]'"
            ) from exc

        actual_device = resolve_device(self.requested_device)
        LOGGER.info("Đang tải embedding model %s trên %s", self.model_name, actual_device)

        model = SentenceTransformer(self.model_name, device=actual_device)
        dimension = int(model.get_sentence_embedding_dimension() or 0)
        if dimension != self.expected_dimension:
            raise RuntimeError(
                f"Model trả vector {dimension} chiều; index cần "
                f"{self.expected_dimension} chiều."
            )

        LOGGER.info("Embedding device thực tế: %s", model.device)
        self._model = model

    def embed(self, text: str) -> list[float]:
        """Return a normalized embedding for ``text`` (cosine-ready)."""
        self._load()
        vector = self._model.encode(
            [text],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]

        if len(vector) != self.expected_dimension:
            raise RuntimeError(
                f"Query vector có {len(vector)} chiều, kỳ vọng {self.expected_dimension}."
            )

        return [float(value) for value in vector.tolist()]

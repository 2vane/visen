"""Lazy cross-encoder reranker (bge-reranker-v2-m3) for fused candidates.

``transformers`` / ``torch`` load only on first scoring call, keeping the
package importable without the ``neo4j`` extra.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from vsentinel.retrievers.devices import resolve_device

LOGGER = logging.getLogger("vsentinel.retrievers.reranker")


class CrossEncoderReranker:
    """Cross-encoder reranker loaded lazily.

    Scores each ``[query, passage]`` pair directly, unlike the bi-encoder
    embedder which encodes query and passage separately.
    """

    def __init__(
        self,
        model_name: str,
        device: str,
        batch_size: int,
        max_length: int,
        use_fp16: bool,
    ) -> None:
        self.model_name = model_name
        self.requested_device = device
        self.batch_size = batch_size
        self.max_length = max_length
        self.use_fp16 = use_fp16

        self.device: Optional[str] = None
        self.tokenizer: Any = None
        self.model: Any = None
        self.torch: Any = None

    def _load(self) -> None:
        if self.model is not None:
            return

        try:
            import torch
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Reranking cần transformers và PyTorch. Cài extra: "
                "pip install 'vsentinel[neo4j]'"
            ) from exc

        actual_device = resolve_device(self.requested_device)
        fp16_enabled = self.use_fp16 and actual_device.startswith("cuda")
        dtype = torch.float16 if fp16_enabled else torch.float32

        LOGGER.info(
            "Đang tải reranker %s trên %s | fp16=%s",
            self.model_name,
            actual_device,
            fp16_enabled,
        )

        tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name,
            torch_dtype=dtype,
        )
        model.to(actual_device)
        model.eval()

        self.torch = torch
        self.tokenizer = tokenizer
        self.model = model
        self.device = actual_device

    def score_pairs(
        self,
        pairs: list[tuple[str, str]],
        normalize: bool = True,
    ) -> list[float]:
        if not pairs:
            return []

        self._load()
        assert self.tokenizer is not None
        assert self.model is not None
        assert self.torch is not None
        assert self.device is not None

        scores: list[float] = []

        for start in range(0, len(pairs), self.batch_size):
            batch = pairs[start:start + self.batch_size]
            queries = [query for query, _ in batch]
            passages = [passage for _, passage in batch]

            encoded = self.tokenizer(
                queries,
                passages,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            )
            encoded = {
                name: tensor.to(self.device)
                for name, tensor in encoded.items()
            }

            with self.torch.inference_mode():
                logits = self.model(
                    **encoded,
                    return_dict=True,
                ).logits.view(-1).float()

                if normalize:
                    logits = self.torch.sigmoid(logits)

            scores.extend(float(value) for value in logits.cpu().tolist())

        return scores

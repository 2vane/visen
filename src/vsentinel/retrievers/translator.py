"""Lazy NLLB translator for cross-language (dual) query expansion.

``transformers`` / ``torch`` load only when a cross-language query is actually
needed, so the package imports without the ``neo4j`` extra.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from vsentinel.retrievers.devices import resolve_device
from vsentinel.retrievers.neo4j_config import LANGUAGE_CODES
from vsentinel.retrievers.text_utils import clean_text

LOGGER = logging.getLogger("vsentinel.retrievers.translator")


class LocalTranslator:
    """NLLB translator loaded lazily; only used for cross-language queries."""

    def __init__(self, model_name: str, device: str) -> None:
        self.model_name = model_name
        self.requested_device = device
        self.device: Optional[str] = None
        self.tokenizer: Any = None
        self.model: Any = None
        self.torch: Any = None
        self.cache: dict[tuple[str, str, str], str] = {}

    def _load(self) -> None:
        if self.model is not None:
            return

        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Dual-query cần transformers và sentencepiece. Cài extra: "
                "pip install 'vsentinel[neo4j]'"
            ) from exc

        actual_device = resolve_device(self.requested_device)
        LOGGER.info(
            "Đang tải translation model %s trên %s",
            self.model_name,
            actual_device,
        )

        dtype = torch.float16 if actual_device.startswith("cuda") else torch.float32
        tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(
            self.model_name,
            torch_dtype=dtype,
        )
        model.to(actual_device)
        model.eval()

        self.torch = torch
        self.tokenizer = tokenizer
        self.model = model
        self.device = actual_device

    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        max_new_tokens: int,
    ) -> str:
        if source_language == target_language:
            return text

        key = (text, source_language, target_language)
        if key in self.cache:
            return self.cache[key]

        if source_language not in LANGUAGE_CODES or target_language not in LANGUAGE_CODES:
            raise ValueError(
                f"Không hỗ trợ translation {source_language}->{target_language}."
            )

        self._load()
        assert self.tokenizer is not None
        assert self.model is not None
        assert self.torch is not None
        assert self.device is not None

        source_code = LANGUAGE_CODES[source_language]
        target_code = LANGUAGE_CODES[target_language]
        self.tokenizer.src_lang = source_code

        encoded = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        )
        encoded = {
            name: tensor.to(self.device)
            for name, tensor in encoded.items()
        }

        target_token_id = self.tokenizer.convert_tokens_to_ids(target_code)
        if (
            target_token_id is None
            or target_token_id < 0
            or target_token_id == self.tokenizer.unk_token_id
        ):
            raise RuntimeError(
                f"Translation tokenizer không có language token {target_code}."
            )

        with self.torch.inference_mode():
            generated = self.model.generate(
                **encoded,
                forced_bos_token_id=target_token_id,
                max_new_tokens=max_new_tokens,
                num_beams=4,
                early_stopping=True,
            )

        translated = clean_text(
            self.tokenizer.batch_decode(
                generated,
                skip_special_tokens=True,
            )[0]
        )
        if not translated:
            raise RuntimeError("Translation model trả về chuỗi rỗng.")

        self.cache[key] = translated
        return translated

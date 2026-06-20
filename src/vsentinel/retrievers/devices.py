"""Torch device resolution for the Neo4j retriever's models.

``torch`` is imported lazily so the package imports cleanly without the
``neo4j`` extra installed.
"""
from __future__ import annotations


def resolve_device(requested: str) -> str:
    """Resolve ``auto`` to the best available device; validate explicit choices."""
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Thiếu PyTorch.") from exc

    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if (
            getattr(torch.backends, "mps", None)
            and torch.backends.mps.is_available()
        ):
            return "mps"
        return "cpu"

    if requested.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError(
            "Bạn chọn CUDA nhưng PyTorch không hỗ trợ CUDA trong môi trường này. "
            f"torch={torch.__version__}, torch.version.cuda={torch.version.cuda}"
        )

    return requested

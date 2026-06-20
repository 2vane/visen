"""Pure routing / fusion / reranking helpers — stdlib only.

These hold no model or DB state, so they import freely without the ``neo4j``
extra and are unit-testable in isolation.
"""
from __future__ import annotations

from typing import Any, Iterable

from vsentinel.retrievers.neo4j_config import CORPORA, ROUTER_TERMS
from vsentinel.retrievers.text_utils import clean_text


def router_scores(question: str, router_terms: dict = ROUTER_TERMS) -> dict[str, int]:
    """Score each corpus by keyword overlap; longer phrases weigh more."""
    normalized = clean_text(question).casefold()
    scores: dict[str, int] = {}

    for corpus, terms in router_terms.items():
        score = 0
        for term in terms:
            if term.casefold() in normalized:
                # Longer phrases are more discriminative than single words.
                score += max(1, min(4, len(term.split())))
        scores[corpus] = score

    return scores


def select_corpora(
    question: str,
    law: str,
    corpora: dict = CORPORA,
    router_terms: dict = ROUTER_TERMS,
    fallback: list[str] | None = None,
) -> tuple[list[str], dict[str, int]]:
    """Pick which corpora to query: explicit law, all, or router-driven auto.

    ``fallback`` is the corpus list used when 'auto' routing finds no keyword
    match; defaults to every corpus when not supplied.
    """
    if law in corpora:
        return [law], router_scores(question, router_terms)

    if law == "all":
        return list(corpora), router_scores(question, router_terms)

    scores = router_scores(question, router_terms)
    best = max(scores.values(), default=0)

    if best == 0:
        # Uncertain: use the caller's fallback (e.g. the governing law for the
        # query's language) rather than blindly querying every corpus.
        return (list(fallback) if fallback else list(corpora)), scores

    # Keep near-ties so EdTech queries can hit FERPA and COPPA together.
    selected = [
        corpus
        for corpus, score in scores.items()
        if score > 0 and score >= best - 1
    ]
    return selected or list(corpora), scores


def fuse_hits(rows: Iterable[dict[str, Any]], rrf_k: int) -> list[dict[str, Any]]:
    """Merge per-query results with Reciprocal Rank Fusion.

    Each appearance of a node at rank ``r`` adds ``1 / (rrf_k + r)``. The best
    raw vector score is preserved for display and tie-breaking.
    """
    fused: dict[str, dict[str, Any]] = {}

    for row in rows:
        node_id = str(row.get("id") or "")
        if not node_id:
            continue

        rank = max(1, int(row.get("query_rank") or 1))
        contribution = 1.0 / (rrf_k + rank)
        query_record = {
            "variant": str(row.get("query_variant") or "original"),
            "language": str(row.get("query_language") or ""),
            "text": str(row.get("query_text") or ""),
            "rank": rank,
            "score": float(row.get("score") or 0.0),
            "rrf_contribution": contribution,
        }

        if node_id not in fused:
            item = dict(row)
            item["fusion_score"] = contribution
            item["matched_queries"] = [query_record]
            item["score"] = float(row.get("score") or 0.0)
            fused[node_id] = item
            continue

        item = fused[node_id]
        item["fusion_score"] = float(item["fusion_score"]) + contribution
        item["matched_queries"].append(query_record)

        if float(row.get("score") or 0.0) > float(item.get("score") or 0.0):
            preserved_fusion = item["fusion_score"]
            preserved_matches = item["matched_queries"]
            best = dict(row)
            best["fusion_score"] = preserved_fusion
            best["matched_queries"] = preserved_matches
            best["score"] = float(row.get("score") or 0.0)
            fused[node_id] = best

    return sorted(
        fused.values(),
        key=lambda row: (
            float(row.get("fusion_score") or 0.0),
            float(row.get("score") or 0.0),
        ),
        reverse=True,
    )


def build_rerank_passage(row: dict[str, Any]) -> str:
    """Build a metadata-rich passage for the cross-encoder (pre-context-expand)."""
    fields = [
        ("Law", row.get("document_citation")),
        ("Corpus", row.get("corpus_name")),
        ("Citation", row.get("citation")),
        ("Section", row.get("section_title")),
        ("Defined term", row.get("term")),
        ("Type", row.get("kind")),
        ("Text", row.get("text")),
    ]
    return "\n".join(
        f"{label}: {clean_text(value)}"
        for label, value in fields
        if clean_text(value)
    )


def choose_rerank_variants(
    variants: list[dict[str, str]],
    mode: str,
) -> list[dict[str, str]]:
    if not variants:
        return []

    if mode == "original":
        originals = [item for item in variants if item.get("variant") == "original"]
        return originals or variants[:1]

    if mode == "translated":
        translated = [item for item in variants if item.get("variant") == "translated"]
        return translated or variants[:1]

    return variants


def rerank_rows(
    rows: list[dict[str, Any]],
    query_variants: dict[str, list[dict[str, str]]],
    reranker,
    rerank_top_n: int,
    query_mode: str,
    min_reranker_score: float,
) -> list[dict[str, Any]]:
    """Re-score the top fused candidates with a cross-encoder.

    Each candidate is scored against its corpus's original and/or translated
    query; the final score is the max, so a poor translation can't sink a good
    candidate.
    """
    candidates = [dict(row) for row in rows[:rerank_top_n]]
    pairs: list[tuple[str, str]] = []
    metadata: list[tuple[int, dict[str, str]]] = []

    for candidate_index, row in enumerate(candidates):
        passage = build_rerank_passage(row)
        variants = choose_rerank_variants(
            query_variants.get(str(row.get("corpus"))) or [],
            query_mode,
        )

        if not variants:
            variants = [{
                "variant": "fallback",
                "language": "",
                "text": str(row.get("query_text") or ""),
            }]

        for variant in variants:
            query_text = clean_text(variant.get("text"))
            if not query_text:
                continue
            pairs.append((query_text, passage))
            metadata.append((candidate_index, variant))

    scores = reranker.score_pairs(pairs, normalize=True)
    if len(scores) != len(metadata):
        raise RuntimeError("Số reranker scores không khớp số query-passage pairs.")

    grouped: dict[int, list[dict[str, Any]]] = {}
    for score, (candidate_index, variant) in zip(scores, metadata):
        grouped.setdefault(candidate_index, []).append({
            "variant": variant.get("variant"),
            "language": variant.get("language"),
            "query": variant.get("text"),
            "score": float(score),
        })

    reranked: list[dict[str, Any]] = []
    for candidate_index, row in enumerate(candidates):
        details = grouped.get(candidate_index, [])
        row["reranker_scores"] = details
        row["reranker_score"] = (
            max(item["score"] for item in details) if details else None
        )

        if (
            row["reranker_score"] is not None
            and float(row["reranker_score"]) >= min_reranker_score
        ):
            reranked.append(row)

    reranked.sort(
        key=lambda row: (
            float(row.get("reranker_score") or 0.0),
            float(row.get("fusion_score") or 0.0),
            float(row.get("score") or 0.0),
        ),
        reverse=True,
    )
    return reranked

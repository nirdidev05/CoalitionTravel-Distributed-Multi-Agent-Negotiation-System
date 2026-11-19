"""Pure retrieval metrics used by offline tests and the evaluation CLI."""

from math import log2


def score_query(retrieved_ids: list[str], relevant_grades: dict[str, int], top_k: int) -> dict:
    if top_k < 1:
        raise ValueError("top_k must be positive")
    ranked = retrieved_ids[:top_k]
    relevant = {chunk_id: grade for chunk_id, grade in relevant_grades.items() if grade > 0}
    hits = [chunk_id for chunk_id in ranked if chunk_id in relevant]
    reciprocal_rank = next(
        (1 / rank for rank, chunk_id in enumerate(ranked, 1) if chunk_id in relevant), 0.0
    )
    dcg = sum(
        (2 ** relevant[chunk_id] - 1) / log2(rank + 1)
        for rank, chunk_id in enumerate(ranked, 1)
        if chunk_id in relevant
    )
    ideal = sorted(relevant.values(), reverse=True)[:top_k]
    idcg = sum((2**grade - 1) / log2(rank + 1) for rank, grade in enumerate(ideal, 1))
    return {
        "precision": len(hits) / top_k,
        "recall": len(hits) / len(relevant) if relevant else 0.0,
        "reciprocal_rank": reciprocal_rank,
        "ndcg": dcg / idcg if idcg else 0.0,
        "relevant_retrieved": len(hits),
        "relevant_total": len(relevant),
    }

"""Smart search module for KubeCoach using TF-IDF and Cosine Similarity.

Converts Kubernetes knowledge records into TF-IDF vector representations
and calculates cosine similarity against incoming student queries to rank
and retrieve the top most relevant documentation records.
"""

import logging
from typing import Any, Dict, List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.records import load_records

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kubecoach.smart_search")


def build_corpus_document(record: Dict[str, Any]) -> str:
    """Concatenate relevant text fields of a record into a searchable document."""
    rec_id = str(record.get("id", "")).strip()
    title = str(record.get("page_title", "")).strip()
    category = str(record.get("category", "")).strip()
    definition = str(record.get("one_line_definition", "")).strip()
    command = str(record.get("key_kubectl_command", "")).strip()
    limit = str(record.get("limit_or_default", "")).strip()

    # Heavily weight ID and title to ensure direct concept queries rank at the top
    return f"{rec_id} {rec_id} {rec_id} {title} {title} {category} {definition} {command} {limit}".strip()


def smart_search(
    query: str,
    records: Optional[List[Dict[str, Any]]] = None,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Rank Kubernetes records against a natural language query using TF-IDF & Cosine Similarity.

    Args:
        query: User search query.
        records: Optional list of record dicts. If omitted, loads from data/records.json.
        top_k: Number of top results to return (default: 3).

    Returns:
        List of matching record dictionaries with an added 'score' field (float),
        sorted in descending order of relevance.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        logger.debug("Empty query passed to smart_search; returning empty results.")
        return []

    dataset = records if records is not None else load_records()
    if not dataset:
        logger.warning("Empty records dataset passed to smart_search.")
        return []

    # 1. Build document corpus
    corpus = [build_corpus_document(rec) for rec in dataset]

    # 2. Compute TF-IDF representation
    # token_pattern allows alphanumeric and hyphens/underscores for kubectl subcommands
    vectorizer = TfidfVectorizer(
        stop_words="english",
        token_pattern=r"(?u)\b[a-zA-Z0-9_\-]+\b",
        sublinear_tf=True,
    )

    try:
        tfidf_matrix = vectorizer.fit_transform(corpus)
        query_vector = vectorizer.transform([cleaned_query])
    except ValueError as exc:
        # Occurs if query contains only stopwords or unknown tokens
        logger.debug("TF-IDF vectorizer encountered empty vocabulary: %s", exc)
        return []

    # 3. Calculate Cosine Similarity
    similarity_scores = cosine_similarity(query_vector, tfidf_matrix).flatten()

    # 4. Rank results
    ranked_indices = similarity_scores.argsort()[::-1]

    results: List[Dict[str, Any]] = []
    for idx in ranked_indices:
        score = float(similarity_scores[idx])
        if score <= 0.0:
            # Skip records with zero similarity
            continue

        rec_copy = dict(dataset[idx])
        rec_copy["score"] = round(score, 4)
        results.append(rec_copy)

        if len(results) >= top_k:
            break

    logger.info(
        "Smart search for '%s' returned %d results (top score: %s)",
        cleaned_query,
        len(results),
        results[0]["score"] if results else "0.0",
    )
    return results


def main() -> None:
    """CLI tester for smart search."""
    print("=" * 60)
    print("KubeCoach — TF-IDF Smart Search CLI Tester")
    print("=" * 60)
    sample_queries = [
        "How do I manage pods and rollout updates?",
        "deployment",
        "What exposes network service to containers?",
        "Where do I store secrets or passwords?",
        "kubectl get ingress",
    ]

    for q in sample_queries:
        print(f"\nQuery: '{q}'")
        matches = smart_search(q, top_k=2)
        if not matches:
            print("  No relevant records found.")
        for rank, m in enumerate(matches, 1):
            print(f"  {rank}. [{m['id']}] {m['page_title']} (score: {m['score']})")
            print(f"     Definition: {m['one_line_definition']}")
            print(f"     Command: {m['key_kubectl_command']}")


if __name__ == "__main__":
    main()

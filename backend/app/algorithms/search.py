"""Content-based document search using TF-IDF and cosine similarity."""

from sklearn.metrics.pairwise import cosine_similarity


def search_documents(
    vectorizer,
    matrix,
    query: str,
    top_k: int = 10,
    min_score: float = 0.01,
) -> list[tuple[int, float, list[str]]]:
    """Rank documents against a query.

    Returns a list of (document index, similarity score, matched keywords).
    """
    if not query or not query.strip():
        return []

    query_vec = vectorizer.transform([query])

    # No query terms exist in the fitted document vocabulary.
    if query_vec.nnz == 0:
        return []

    scores = cosine_similarity(query_vec, matrix).ravel()
    terms = vectorizer.get_feature_names_out()
    query_weights = query_vec.toarray().ravel()

    results = []

    for index in scores.argsort()[::-1][:top_k]:
        score = float(scores[index])

        if score < min_score:
            break

        document_weights = matrix[index].toarray().ravel()
        contributions = query_weights * document_weights
        top_indices = contributions.argsort()[::-1][:5]

        keywords = [
            str(terms[term_index])
            for term_index in top_indices
            if contributions[term_index] > 0
        ]

        results.append((int(index), score, keywords))

    return results


def make_snippet(text: str, keywords: list[str], width: int = 160) -> str:
    """Return a short excerpt around a matched keyword when possible."""
    lower_text = text.lower()

    for keyword in keywords:
        position = lower_text.find(keyword.split()[0])

        if position != -1:
            start = max(0, position - width // 2)
            end = min(len(text), position + width // 2)

            snippet = " ".join(text[start:end].split())
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(text) else ""

            return f"{prefix}{snippet}{suffix}"

    snippet = " ".join(text[:width].split())
    return snippet + ("..." if len(text) > width else "")

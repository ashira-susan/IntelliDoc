"""Content-based document similarity using TF-IDF and cosine similarity."""

from itertools import combinations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def build_tfidf(texts: list[str]):
    """Convert document texts into TF-IDF feature vectors.

    Returns:
        A tuple containing the fitted vectorizer and TF-IDF matrix.
    """
    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        sublinear_tf=True,
    )

    matrix = vectorizer.fit_transform(texts)
    return vectorizer, matrix


def shared_keywords(vectorizer, matrix, first_index: int, second_index: int,
                    limit: int = 5) -> list[str]:
    """Return prominent terms shared by two documents."""
    first_vector = matrix[first_index].toarray().ravel()
    second_vector = matrix[second_index].toarray().ravel()

    shared_indices = [
        index
        for index, (first_weight, second_weight) in enumerate(
            zip(first_vector, second_vector)
        )
        if first_weight > 0 and second_weight > 0
    ]

    shared_indices.sort(
        key=lambda index: min(
            first_vector[index],
            second_vector[index],
        ),
        reverse=True,
    )

    feature_names = vectorizer.get_feature_names_out()

    return [
        str(feature_names[index])
        for index in shared_indices[:limit]
    ]


def similar_pairs(
    texts: list[str],
    threshold: float = 0.10,
) -> list[dict]:
    """Find document pairs whose cosine similarity meets the threshold.

    Each result contains the two document indexes and their similarity score.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")

    if len(texts) < 2:
        return []

    cleaned_texts = [
        text.strip() if text and text.strip() else " "
        for text in texts
    ]

    try:
        vectorizer, matrix = build_tfidf(cleaned_texts)
    except ValueError:
        # For example, every document may be empty or contain only stop words.
        return []

    scores = cosine_similarity(matrix)
    results = []

    for first_index, second_index in combinations(range(len(texts)), 2):
        score = float(scores[first_index, second_index])

        if score >= threshold:
            results.append(
                {
                    "first_index": first_index,
                    "second_index": second_index,
                    "score": score,
                    "shared_keywords": shared_keywords(
                        vectorizer,
                        matrix,
                        first_index,
                        second_index,
                    ),
                }
            )

    return sorted(
        results,
        key=lambda pair: pair["score"],
        reverse=True,
    )

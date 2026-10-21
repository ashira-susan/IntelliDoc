from app.algorithms.search import make_snippet, search_documents
from app.algorithms.similarity import build_tfidf


TEXTS = [
    "distance vector routing protocol used in computer networks",
    "database normalization with sql tables and keys",
    "pasta recipe with tomato sauce and basil",
]


def test_relevant_document_ranked_first():
    vectorizer, matrix = build_tfidf(TEXTS)

    results = search_documents(
        vectorizer, matrix, "distance vector routing"
    )

    assert results
    assert results[0][0] == 0
    assert results[0][1] > 0
    assert "routing" in results[0][2]


def test_query_with_unknown_words_returns_nothing():
    vectorizer, matrix = build_tfidf(TEXTS)

    results = search_documents(
        vectorizer, matrix, "quantum chromodynamics"
    )

    assert results == []


def test_stopword_only_query_returns_nothing():
    vectorizer, matrix = build_tfidf(TEXTS)

    results = search_documents(
        vectorizer, matrix, "the and of"
    )

    assert results == []


def test_search_is_case_insensitive():
    vectorizer, matrix = build_tfidf(TEXTS)

    lower_results = search_documents(vectorizer, matrix, "routing")
    upper_results = search_documents(vectorizer, matrix, "ROUTING")

    assert lower_results
    assert upper_results
    assert lower_results[0][0] == upper_results[0][0]


def test_snippet_contains_keyword():
    snippet = make_snippet(TEXTS[0], ["routing"])

    assert "routing" in snippet

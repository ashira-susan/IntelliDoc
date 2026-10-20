import pytest

from app.algorithms.similarity import (
    build_tfidf,
    shared_keywords,
    similar_pairs,
)


def test_related_documents_have_higher_similarity_than_unrelated_documents():
    texts = [
        "Routing protocols forward packets across computer networks.",
        "Network routing protocols select paths for packet forwarding.",
        "Cooking pasta requires boiling water and adding salt.",
    ]

    pairs = similar_pairs(texts, threshold=0.0)

    scores = {
        (pair["first_index"], pair["second_index"]): pair["score"]
        for pair in pairs
    }

    related_score = scores[(0, 1)]
    unrelated_score = scores[(0, 2)]

    assert related_score > unrelated_score


def test_identical_texts_have_similarity_of_one():
    texts = [
        "Computer networks use routing protocols.",
        "Computer networks use routing protocols.",
    ]

    pairs = similar_pairs(texts, threshold=0.0)

    assert len(pairs) == 1
    assert pairs[0]["score"] == pytest.approx(1.0)


def test_threshold_filters_pairs():
    texts = [
        "Routing protocols forward packets across networks.",
        "Routing protocols select paths for packet forwarding.",
    ]

    all_pairs = similar_pairs(texts, threshold=0.0)
    strict_pairs = similar_pairs(texts, threshold=1.0)

    assert len(all_pairs) == 1
    assert all(pair["score"] >= 1.0 for pair in strict_pairs)
    assert len(strict_pairs) <= len(all_pairs)


def test_empty_or_unusable_text_returns_no_pairs():
    assert similar_pairs(["", "   "]) == []
    assert similar_pairs(["the and is", "a an the"]) == []


def test_shared_keywords_identifies_overlapping_terms():
    texts = [
        "Routing protocols forward packets.",
        "Routing protocols select packet routes.",
    ]

    vectorizer, matrix = build_tfidf(texts)
    keywords = shared_keywords(vectorizer, matrix, 0, 1)

    assert keywords
    assert any("routing" in keyword or "protocol" in keyword
               for keyword in keywords)


def test_single_document_returns_no_pairs():
    assert similar_pairs(["Routing protocols forward packets."]) == []


def test_invalid_threshold_is_rejected():
    with pytest.raises(ValueError):
        similar_pairs(["routing packets", "network routing"], threshold=-0.1)

    with pytest.raises(ValueError):
        similar_pairs(["routing packets", "network routing"], threshold=1.1)

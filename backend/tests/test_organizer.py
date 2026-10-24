from app.algorithms.organizer import cluster_documents, folder_name
from app.algorithms.similarity import build_tfidf


TEXTS = [
    "distance vector routing protocol computes shortest path between network routers",
    "routing protocol uses distance vector algorithm to find shortest path in network routers",
    "database normalization removes redundancy using normal forms in relational tables",
    "relational database tables use normal forms and normalization to remove redundancy",
]


def test_topics_are_clustered_together():
    _, matrix = build_tfidf(TEXTS)

    clusters = sorted(
        sorted(cluster)
        for cluster in cluster_documents(matrix, 0.85)
    )

    assert clusters == [[0, 1], [2, 3]]


def test_tiny_threshold_keeps_documents_apart():
    _, matrix = build_tfidf(TEXTS)

    assert len(cluster_documents(matrix, 0.01)) == 4


def test_single_document_is_one_cluster():
    _, matrix = build_tfidf(["only one document here"])

    assert cluster_documents(matrix, 0.8) == [[0]]


def test_folder_name_reflects_topic():
    vectorizer, matrix = build_tfidf(TEXTS)

    name = folder_name(vectorizer, matrix, [0, 1]).lower()

    assert any(
        word in name
        for word in ("routing", "distance", "vector", "network", "path")
    )


def test_folder_name_is_clean_text():
    vectorizer, matrix = build_tfidf(TEXTS)

    name = folder_name(vectorizer, matrix, [2, 3])

    assert name
    assert "/" not in name

"""Cluster related documents and generate suggested folder names."""

import numpy as np
from sklearn.cluster import AgglomerativeClustering


def cluster_documents(matrix, distance_threshold):
    """Group document indices using cosine distance."""
    n = matrix.shape[0]

    if n < 2:
        return [list(range(n))]

    model = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
    )

    labels = model.fit_predict(matrix.toarray())

    clusters = {}
    for index, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(index)

    return list(clusters.values())


def folder_name(vectorizer, matrix, indices, top_n=2):
    """Generate a readable folder name from a cluster's key terms."""
    terms = vectorizer.get_feature_names_out()
    centroid = np.asarray(matrix[indices].mean(axis=0)).ravel()

    words = []

    for k in centroid.argsort()[::-1]:
        if centroid[k] <= 0 or len(words) >= top_n:
            break

        term = str(terms[k])

        # Prefer individual words for short, readable folder names.
        if " " in term:
            continue

        words.append(term)

    return " ".join(words).title() if words else "Miscellaneous"

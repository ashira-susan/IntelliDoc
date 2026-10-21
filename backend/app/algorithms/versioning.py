import re
from difflib import SequenceMatcher

W_CONTENT, W_FILENAME, W_DATE = 0.60, 0.25, 0.15


def normalize_filename(name: str) -> str:
    stem = name.lower().rsplit(".", 1)[0]
    stem = re.sub(r"\(\d+\)", " ", stem)  # "(1)" copies
    stem = re.sub(r"[_\-.\[\]()]+", " ", stem)
    stem = re.sub(r"\b(?:v|ver|version|rev|revision)\s*\d+\b", " ", stem)
    stem = re.sub(
        r"\b(?:final|latest|newest|new|old|copy|draft|revised|edited|"
        r"updated|backup)\d*\b",
        " ",
        stem,
    )
    cleaned = " ".join(stem.split())
    return cleaned or " ".join(name.lower().rsplit(".", 1)[0].split())


def filename_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_filename(a), normalize_filename(b)).ratio()


def date_proximity(a, b, window_days: int = 30):
    if a is None or b is None:
        return None
    days = abs((a - b).total_seconds()) / 86400
    return max(0.0, 1.0 - days / window_days)


def family_score(content: float, filename: float, date):
    if date is None:
        return (W_CONTENT * content + W_FILENAME * filename) / (W_CONTENT + W_FILENAME)
    return W_CONTENT * content + W_FILENAME * filename + W_DATE * date


def group_indices(n: int, edges):
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in edges:
        parent[find(i)] = find(j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [g for g in groups.values() if len(g) > 1]
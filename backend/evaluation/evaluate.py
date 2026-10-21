import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sklearn.metrics.pairwise import cosine_similarity

from app.algorithms.similarity import build_tfidf

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "dataset" / "documents"
TRUTH = ROOT / "dataset" / "ground_truth.csv"


def load_truth():
    related, duplicate = set(), set()

    with open(TRUTH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = frozenset(
                (row["doc_a"].strip(), row["doc_b"].strip())
            )
            kind = row["relationship"].strip().lower()

            if kind == "related":
                related.add(key)
            elif kind == "duplicate":
                duplicate.add(key)
            elif kind != "unrelated":
                raise ValueError(
                    f"Unknown relationship value: {kind!r}"
                )

    return related, duplicate


def main():
    files = sorted(DOCS.glob("*.txt"))
    names = [p.name for p in files]
    texts = [
        p.read_text(encoding="utf-8", errors="ignore")
        for p in files
    ]

    related, duplicate = load_truth()

    if not files:
        raise ValueError(f"No .txt documents found in {DOCS}")

    known_names = set(names)
    for pair in related | duplicate:
        missing = pair - known_names
        if missing:
            raise ValueError(
                f"Ground-truth filenames not found in dataset: "
                f"{sorted(missing)}"
            )

    _, matrix = build_tfidf(texts)
    sim = cosine_similarity(matrix)

    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            key = frozenset((names[i], names[j]))

            # Exact duplicates are evaluated separately by SHA-256.
            if key in duplicate:
                continue

            pairs.append(
                (float(sim[i, j]), key in related, names[i], names[j])
            )

    total_related = sum(pair[1] for pair in pairs)

    print(
        f"{len(names)} documents, {len(pairs)} pairs evaluated, "
        f"{total_related} labelled related pairs\n"
    )
    print("threshold  precision  recall     f1     TP  FP  FN")

    best = (0.0, -1.0)

    for k in range(1, 19):
        threshold = k * 0.05

        tp = sum(
            1 for score, is_related, _, _ in pairs
            if score >= threshold and is_related
        )
        fp = sum(
            1 for score, is_related, _, _ in pairs
            if score >= threshold and not is_related
        )
        fn = sum(
            1 for score, is_related, _, _ in pairs
            if score < threshold and is_related
        )

        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall else 0.0
        )

        print(
            f"{threshold:8.2f}  {precision:9.2f}  "
            f"{recall:6.2f}  {f1:7.2f}  "
            f"{tp:3d} {fp:3d} {fn:3d}"
        )

        if f1 > best[1]:
            best = (threshold, f1)

    threshold = best[0]
    print(
        f"\nBest threshold by F1: {threshold:.2f} "
        f"(F1 = {best[1]:.2f})"
    )
    print("\nMistakes at that threshold:")

    for score, is_related, name_a, name_b in sorted(
        pairs, reverse=True
    ):
        if score >= threshold and not is_related:
            print(
                f"  FALSE POSITIVE  {score:.2f}  "
                f"{name_a}  <->  {name_b}"
            )
        elif score < threshold and is_related:
            print(
                f"  MISSED          {score:.2f}  "
                f"{name_a}  <->  {name_b}"
            )


if __name__ == "__main__":
    main()

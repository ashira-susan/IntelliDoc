import { useEffect, useState } from "react";
import { getRelated } from "../services/api";

function RelatedPanel() {
  const [result, setResult] = useState(null);
  const [threshold, setThreshold] = useState(0.1);

  useEffect(() => {
    let cancelled = false;

    getRelated(threshold)
      .then((data) => {
        if (!cancelled) {
          setResult({
            threshold,
            data,
            error: null,
          });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setResult({
            threshold,
            data: null,
            error: err.message,
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [threshold]);

  const currentResult =
    result?.threshold === threshold ? result : null;

  const data = currentResult?.data ?? null;
  const error = currentResult?.error ?? null;
  const loading = currentResult === null;

  return (
    <section style={{ marginTop: "2rem" }}>
      <h2>Related Document Discovery</h2>

      <p>
        Finds documents with similar extracted text using TF-IDF and
        cosine similarity. These are suggestions, not confirmed duplicates.
      </p>

      <label htmlFor="similarity-threshold">
        Minimum similarity: {(threshold * 100).toFixed(0)}%
      </label>
      <br />

      <input
        id="similarity-threshold"
        type="range"
        min="0.05"
        max="0.5"
        step="0.05"
        value={threshold}
        onChange={(event) => setThreshold(Number(event.target.value))}
      />

      {loading && <p>Finding related documents...</p>}

      {error && (
        <p role="alert" style={{ color: "crimson" }}>
          Could not load related documents: {error}
        </p>
      )}

      {!loading && !error && data && (
        <>
          <p>
            Compared {data.documents_compared} documents. Found{" "}
            {data.total_pairs} related pairs.
          </p>

          {data.pairs.length === 0 ? (
            <p>No related pairs found at this threshold.</p>
          ) : (
            <div>
              {data.pairs.map((pair) => (
                <article
                  key={`${pair.doc_a.id}-${pair.doc_b.id}`}
                  style={{
                    border: "1px solid #ddd",
                    borderRadius: "8px",
                    padding: "1rem",
                    marginBottom: "0.75rem",
                  }}
                >
                  <p>
                    <strong>{pair.doc_a.filename}</strong>
                    {" ↔ "}
                    <strong>{pair.doc_b.filename}</strong>
                  </p>

                  <p>
                    Similarity: {(pair.score * 100).toFixed(1)}%
                  </p>

                  <p>
                    <strong>Shared keywords:</strong>{" "}
                    {pair.shared_keywords.length > 0
                      ? pair.shared_keywords.join(", ")
                      : "No prominent shared keywords"}
                  </p>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default RelatedPanel;

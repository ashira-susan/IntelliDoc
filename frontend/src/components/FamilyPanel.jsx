import { useEffect, useState } from "react";
import { getFamilies } from "../services/api";

function FamilyPanel() {
  const [threshold, setThreshold] = useState(0.60);
  const [result, setResult] = useState(null);

  useEffect(() => {
    let cancelled = false;

    getFamilies(threshold)
      .then((data) => {
        if (!cancelled) {
          setResult({ threshold, data, error: null });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setResult({ threshold, data: null, error: err.message });
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

  function formatDate(value) {
    if (!value) return "Modification date unavailable";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return "Modification date unavailable";
    }

    return date.toLocaleString();
  }

  return (
    <section style={{ marginTop: "2rem" }}>
      <h2>Document Version Families</h2>

      <p>
        Groups potentially related document versions using extracted-content
        similarity, filename similarity, and available modification dates.
        A family is a suggestion for review, not proof that the documents
        are versions of one another.
      </p>

      <label htmlFor="family-threshold">
        Family detection threshold: {(threshold * 100).toFixed(0)}%
      </label>
      <br />

      <input
        id="family-threshold"
        type="range"
        min="0.60"
        max="0.99"
        step="0.01"
        value={threshold}
        onChange={(event) => setThreshold(Number(event.target.value))}
      />

      <p>
        Higher thresholds are stricter and may split genuine version
        families. Documents can also be grouped transitively through
        other family members.
      </p>

      {loading && <p>Detecting document version families...</p>}

      {error && (
        <p role="alert" style={{ color: "crimson" }}>
          Could not load version families: {error}
        </p>
      )}

      {!loading && !error && data && (
        <>
          <p>
            Compared {data.documents_compared} documents. Found{" "}
            {data.family_count} families at a minimum content similarity
            of {(data.minimum_content_similarity * 100).toFixed(0)}%.
          </p>

          {data.families.length === 0 ? (
            <p>
              No version families found at this threshold.
              Try lowering the threshold.
            </p>
          ) : (
            data.families.map((family) => (
              <article
                key={family.family_id}
                style={{
                  border: "1px solid #ddd",
                  borderRadius: "8px",
                  padding: "1rem",
                  marginBottom: "0.75rem",
                }}
              >
                <h3>Family {family.family_id}</h3>

                <p>
                  {family.member_count} documents in this family
                </p>

                {family.newest_by_date_id != null && (
                  <p>
                    <strong>Newest by modification date:</strong>{" "}
                    {family.members.find(
                      (member) =>
                        member.id === family.newest_by_date_id
                    )?.filename ?? "Document unavailable"}
                  </p>
                )}

                <ul>
                  {family.members.map((member) => (
                    <li key={member.id} style={{ marginBottom: "0.5rem" }}>
                      <strong>{member.filename}</strong>
                      <br />
                      <span>
                        Modified: {formatDate(member.modified_at)}
                      </span>
                      {member.id === family.newest_by_date_id && (
                        <span> — Newest by date</span>
                      )}
                    </li>
                  ))}
                </ul>

                <details>
                  <summary>View pairwise similarity evidence</summary>

                  {family.pair_scores.length === 0 ? (
                    <p>No pairwise evidence is available.</p>
                  ) : (
                    <ul>
                      {family.pair_scores.map((pair) => (
                        <li
                          key={`${pair.document_a_id}-${pair.document_b_id}`}
                        >
                          Documents {pair.document_a_id} and{" "}
                          {pair.document_b_id}: family score{" "}
                          {(pair.family_score * 100).toFixed(1)}%;
                          content similarity{" "}
                          {(pair.content_similarity * 100).toFixed(1)}%;
                          filename similarity{" "}
                          {(pair.filename_similarity * 100).toFixed(1)}%.
                          {pair.date_proximity == null
                            ? " Date evidence unavailable."
                            : ` Date proximity: ${(pair.date_proximity * 100).toFixed(1)}%.`}
                        </li>
                      ))}
                    </ul>
                  )}
                </details>
              </article>
            ))
          )}

          <p>
            <strong>Important:</strong> Newest by modification date does
            not necessarily mean final, correct, or authoritative.
            Review the documents before deciding which version to keep.
          </p>
        </>
      )}
    </section>
  );
}

export default FamilyPanel;

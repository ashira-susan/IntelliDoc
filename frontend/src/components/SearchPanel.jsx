import { useState } from "react";
import { searchDocuments } from "../services/api";

function SearchPanel() {
  const [query, setQuery] = useState("");
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function runSearch() {
    const trimmed = query.trim();

    if (!trimmed || busy) {
      return;
    }

    setBusy(true);
    setError(null);
    setData(null);

    try {
      const result = await searchDocuments(trimmed);
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={{ marginTop: "2rem" }}>
      <h2>Search Documents</h2>

      <p>
        Search the extracted content of your documents. Results include
        relevance scores, matched keywords, and text snippets.
      </p>

      <div>
        <input
          type="text"
          value={query}
          placeholder="e.g. distance vector routing"
          aria-label="Search document content"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              runSearch();
            }
          }}
          style={{
            width: "70%",
            maxWidth: "500px",
            padding: "0.6rem",
          }}
        />

        <button
          type="button"
          onClick={runSearch}
          disabled={busy || !query.trim()}
          style={{ marginLeft: "0.5rem", padding: "0.6rem" }}
        >
          {busy ? "Searching..." : "Search"}
        </button>
      </div>

      {error && (
        <p role="alert" style={{ color: "crimson" }}>
          Search failed: {error}
        </p>
      )}

      {data && data.total === 0 && (
        <p>No documents match &ldquo;{data.query}&rdquo;.</p>
      )}

      {data && data.total > 0 && (
        <>
          <p>
            Found {data.total} matching document
            {data.total === 1 ? "" : "s"}.
          </p>

          {data.results.map((result) => (
            <article
              key={result.id}
              style={{
                border: "1px solid #ddd",
                borderRadius: "8px",
                padding: "1rem",
                marginBottom: "0.75rem",
              }}
            >
              <p>
                <strong>
                  #{result.id} {result.filename}
                </strong>
                <span style={{ marginLeft: "0.5rem", color: "#555" }}>
                  Relevance: {(result.score * 100).toFixed(1)}%
                </span>
              </p>

              <p>{result.snippet}</p>

              <p style={{ fontSize: "0.9rem", color: "#555" }}>
                <strong>Matched keywords:</strong>{" "}
                {result.matched_keywords.length > 0
                  ? result.matched_keywords.join(", ")
                  : "None"}
              </p>
            </article>
          ))}
        </>
      )}
    </section>
  );
}

export default SearchPanel;

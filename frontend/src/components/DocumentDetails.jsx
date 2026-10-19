import { useEffect, useState } from "react";
import { getDocumentDetails } from "../services/api";

function DocumentDetails({ documentId, onClose }) {
  const [document, setDocument] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);
    setDocument(null);

    getDocumentDetails(documentId)
      .then((data) => {
        if (!cancelled) {
          setDocument(data);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  return (
    <section
      style={{
        border: "1px solid #ddd",
        borderRadius: 8,
        padding: 16,
        margin: "1rem 0",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
        }}
      >
        <h2>Document Details</h2>

        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>

      {loading && <p>Loading document details...</p>}

      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {document && (
        <div>
          <p>
            <strong>Filename:</strong> {document.filename}
          </p>
          <p>
            <strong>Type:</strong> {document.file_type}
          </p>
          <p>
            <strong>Size:</strong> {document.file_size} bytes
          </p>
          <p>
            <strong>Status:</strong> {document.status}
          </p>
          <p>
            <strong>SHA-256:</strong>
          </p>
          <code
            style={{
              display: "block",
              overflowWrap: "anywhere",
              marginBottom: 16,
            }}
          >
            {document.file_hash || "Not available"}
          </code>

          <h3>Extracted Text</h3>

          <pre
            style={{
              whiteSpace: "pre-wrap",
              overflowWrap: "anywhere",
              maxHeight: 350,
              overflowY: "auto",
              padding: 12,
              background: "#f5f5f5",
              borderRadius: 4,
            }}
          >
            {document.extracted_text || "No extractable text available."}
          </pre>
        </div>
      )}
    </section>
  );
}

export default DocumentDetails;

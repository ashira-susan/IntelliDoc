
import { useRef, useState } from "react";
import { uploadDocuments } from "../services/api";

export default function UploadPanel({ onUploaded }) {
  const inputRef = useRef(null);
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState([]);
  const [error, setError] = useState(null);

  async function handleUpload() {
    if (selected.length === 0) return;

    setBusy(true);
    setError(null);
    setResults([]);

    try {
      const data = await uploadDocuments(selected);

      setResults(data.results);
      setSelected([]);

      if (inputRef.current) {
        inputRef.current.value = "";
      }

      onUploaded();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2>Upload documents</h2>

      <p>Supported file types: PDF, DOCX, TXT</p>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.docx,.txt"
        onChange={(event) =>
          setSelected(Array.from(event.target.files || []))
        }
      />

      <button
        type="button"
        onClick={handleUpload}
        disabled={busy || selected.length === 0}
        style={{ marginLeft: "8px" }}
      >
        {busy
          ? "Uploading..."
          : `Upload ${selected.length} file(s)`}
      </button>

      {error && (
        <p style={{ color: "crimson" }}>
          Upload error: {error}
        </p>
      )}

      {results.length > 0 && (
        <div>
          <h3>Upload results</h3>

          <ul>
            {results.map((result, index) => (
              <li
                key={`${result.filename}-${index}`}
                style={{
                  color:
                    result.status === "uploaded"
                      ? "green"
                      : "crimson",
                }}
              >
                {result.filename}: {result.status}
                {result.reason ? ` (${result.reason})` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

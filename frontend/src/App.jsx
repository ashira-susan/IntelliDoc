import DocumentDetails from "./components/DocumentDetails";
import { useCallback, useEffect, useState } from "react";
import DocumentTable from "./components/DocumentTable";
import UploadPanel from "./components/UploadPanel";
import DuplicatePanel from "./components/DuplicatePanel";
import { getDocuments, getHealth, getDuplicates } from "./services/api";

function App() {
  const [health, setHealth] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [duplicates, setDuplicates] = useState(null);
  const [error, setError] = useState(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);

  const loadDocuments = useCallback(() => {
    getDocuments()
      .then(setDocuments)
      .catch((err) => setError(err.message));

    getDuplicates()
      .then(setDuplicates)
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((err) => setError(err.message));

    loadDocuments();
  }, [loadDocuments]);

  const handleViewDocument = (id) => {
    setSelectedDocumentId(id);
  };

  return (
    <div
      style={{ fontFamily: "sans-serif", maxWidth: 800, margin: "2rem auto" }}
    >
      <h1>Mr. IntelliDoc</h1>

      <p>
        API: {health ? health.status : "..."} | Database:{" "}
        {health ? health.database : "..."}
      </p>

      {error && (
        <p style={{ color: "crimson" }}>Backend unreachable: {error}</p>
      )}

      <UploadPanel onUploaded={loadDocuments} />

      <h2>Documents ({documents.length})</h2>
      <DocumentTable
        documents={documents}
        onViewDocument={handleViewDocument}
      />

      {selectedDocumentId !== null && (
       <DocumentDetails
        documentId={selectedDocumentId}
        onClose={() => setSelectedDocumentId(null)}
       />
      )}

      <h2>Exact Duplicate Detection</h2>
      <p>
        Files with identical SHA-256 fingerprints are grouped together.
      </p>
      <DuplicatePanel data={duplicates} />
    </div>
  );
}

export default App;

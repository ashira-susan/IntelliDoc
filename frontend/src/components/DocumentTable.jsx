
function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentTable({ documents }) {
  if (documents.length === 0) {
    return <p>No documents yet. Upload some to get started.</p>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left" }}>
            <th>ID</th>
            <th>Filename</th>
            <th>Type</th>
            <th>Size</th>
            <th>Status</th>
            <th>Uploaded</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id}>
              <td>{doc.id}</td>
              <td>{doc.filename}</td>
              <td>{doc.file_type}</td>
              <td>{formatSize(doc.file_size)}</td>
              <td>{doc.status}</td>
              <td>
                {doc.uploaded_at
                  ? new Date(
                      doc.uploaded_at.endsWith("Z")
                        ? doc.uploaded_at
                        : `${doc.uploaded_at}Z`
                    ).toLocaleString()
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


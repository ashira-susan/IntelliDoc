export default function DuplicatePanel({ data }) {
  if (!data) {
    return <p>Loading duplicates...</p>;
  }

  if (data.total_groups === 0) {
    return <p>No exact duplicates found.</p>;
  }

  return (
    <div>
      {data.duplicate_groups.map((group) => (
        <div
          key={group.hash}
          style={{
            border: "1px solid #ccc",
            borderRadius: 8,
            padding: 12,
            marginBottom: 12,
          }}
        >
          <strong>
            Exact duplicate group ({group.count} files)
          </strong>

          <p style={{ fontSize: 12, color: "#666", margin: "4px 0" }}>
            SHA-256: {group.hash.slice(0, 16)}...
          </p>

          <ul>
            {group.documents.map((d) => (
              <li key={d.id}>
                #{d.id} {d.filename}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}


const API_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export async function getHealth() {
  const response = await fetch(`${API_URL}/api/health`);

  if (!response.ok) {
    throw new Error(`Server responded with ${response.status}`);
  }

  return response.json();
}

export async function getDocuments() {
  const response = await fetch(`${API_URL}/api/documents`);

  if (!response.ok) {
    throw new Error(`Server responded with ${response.status}`);
  }

  return response.json();
}

export async function uploadDocuments(files) {
  const formData = new FormData();

  for (const file of files) {
    formData.append("files", file);
  }

  const response = await fetch(`${API_URL}/api/documents/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed (${response.status})`);
  }

  return response.json();
}

export async function getDuplicates() {
  const response = await fetch(`${API_URL}/api/duplicates`);

  if (!response.ok) {
    throw new Error(`Server responded with ${response.status}`);
  }

  return response.json();
}

export async function getDocumentDetails(id) {
  const response = await fetch(`${API_URL}/api/documents/${id}`);

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("Document not found");
    }

    throw new Error(`Server responded with ${response.status}`);
  }

  return response.json();
}


export async function getRelated(threshold = 0.25) {
  const response = await fetch(
    `${API_URL}/api/related?threshold=${encodeURIComponent(threshold)}`
  );

  if (!response.ok) {
    throw new Error(`Related-document search failed (${response.status})`);
  }

  return response.json();
}


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
    formData.append("last_modified", String(file.lastModified));
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

export async function searchDocuments(query, limit = 10) {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
  });

  const response = await fetch(`${API_URL}/api/search?${params}`);

  if (!response.ok) {
    if (response.status === 400) {
      throw new Error("Please enter a search query.");
    }

    throw new Error(`Search failed (${response.status})`);
  }

  return response.json();
}

export async function getFamilies(threshold = 0.60) {
  const response = await fetch(
    `${API_URL}/api/families?threshold=${encodeURIComponent(threshold)}`
  );

  if (!response.ok) {
    if (response.status === 422) {
      throw new Error("The family-detection threshold must be between 0 and 1.");
    }

    throw new Error(`Version-family detection failed (${response.status})`);
  }

  return response.json();
}

export async function suggestOrganization(distance = 0.8) {
  const params = new URLSearchParams({
    distance: String(distance),
  });

  const response = await fetch(
    `${API_URL}/api/organize/suggest?${params}`
  );

  if (!response.ok) {
    throw new Error(`Organization suggestions failed (${response.status})`);
  }

  return response.json();
}

export async function applyOrganization(folders) {
  const response = await fetch(`${API_URL}/api/organize/apply`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ folders }),
  });

  if (!response.ok) {
    let message = `Applying organization failed (${response.status})`;

    try {
      const data = await response.json();
      if (typeof data.detail === "string") {
        message = data.detail;
      }
    } catch {
      // Keep the fallback message if the response is not JSON.
    }

    throw new Error(message);
  }

  return response.json();
}

export async function undoOperation(operationId) {
  const response = await fetch(
    `${API_URL}/api/organize/undo/${operationId}`,
    { method: "POST" }
  );

  if (!response.ok) {
    let message = `Undo failed (${response.status})`;

    try {
      const data = await response.json();
      if (typeof data.detail === "string") {
        message = data.detail;
      }
    } catch {
      // Keep the fallback message if the response is not JSON.
    }

    throw new Error(message);
  }

  return response.json();
}

export async function getFolders() {
  const response = await fetch(`${API_URL}/api/folders`);

  if (!response.ok) {
    throw new Error(`Loading folders failed (${response.status})`);
  }

  return response.json();
}

export async function getHistory() {
  const response = await fetch(`${API_URL}/api/history`);

  if (!response.ok) {
    throw new Error(`Loading organization history failed (${response.status})`);
  }

  return response.json();
}

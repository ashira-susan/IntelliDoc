import { useCallback, useEffect, useState } from "react";
import {
  suggestOrganization,
  applyOrganization,
  undoOperation,
  getFolders,
  getHistory,
} from "../services/api";

export default function OrganizePanel({ onChanged }) {
  const [proposal, setProposal] = useState(null);
  const [folders, setFolders] = useState([]);
  const [history, setHistory] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [folderData, historyData] = await Promise.all([
      getFolders(),
      getHistory(),
    ]);

    setFolders(folderData);
    setHistory(historyData);
  }, []);

  useEffect(() => {
    refresh().catch((err) => setError(err.message));
  }, [refresh]);

  async function handleSuggest() {
    setBusy(true);
    setError("");
    setMessage("");

    try {
      const data = await suggestOrganization();

      if (!data.folders || data.folders.length === 0) {
        setProposal(null);
        setMessage(data.message || "No folder suggestions are available.");
        return;
      }

      setProposal(data.folders);
      setMessage("Review the suggestions and rename folders if needed.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function renameFolder(index, newName) {
    setProposal((current) =>
      current.map((folder, i) =>
        i === index ? { ...folder, name: newName } : folder
      )
    );
  }

  async function handleConfirm() {
    if (!proposal) return;

    const preparedFolders = proposal.map((folder) => ({
      name: folder.name.trim(),
      document_ids: folder.documents.map((doc) => doc.id),
    }));

    if (
      preparedFolders.some(
        (folder) =>
          !folder.name ||
          folder.name === "." ||
          folder.name === ".." ||
          /[\\/:*?"<>|]/.test(folder.name)
      )
    ) {
      setError(
        'Folder names cannot be empty or contain \\ / : * ? " < > | characters.'
      );
      return;
    }

    if (
      !window.confirm(
        "Apply these folder assignments? This changes virtual folder labels, not physical files."
      )
    ) {
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");

    try {
      const result = await applyOrganization(preparedFolders);
      setProposal(null);
      setMessage(
        `Organization applied successfully. ${result.moved} document(s) updated.`
      );
      await refresh();

      if (onChanged) {
        await onChanged();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleUndo(operationId) {
    if (
      !window.confirm(
        "Undo this organization operation and restore previous folder assignments?"
      )
    ) {
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");

    try {
      const result = await undoOperation(operationId);
      setMessage(
        `Undo completed. ${result.restored} document(s) restored.`
      );
      await refresh();

      if (onChanged) {
        await onChanged();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const latestApplied = history.find(
    (operation) => operation.status === "applied"
  );

  return (
    <section className="organize-panel">
      <h2>Organize Documents</h2>

      <p>
        Get content-based folder suggestions, review them, and confirm
        before any folder assignments change. Original files are not moved.
      </p>

      <button onClick={handleSuggest} disabled={busy}>
        {busy ? "Please wait..." : "Suggest Folders"}
      </button>

      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}

      {proposal && (
        <div className="organization-proposal">
          <h3>Review Suggested Folders</h3>

          {proposal.map((folder, index) => (
            <div
              key={`${folder.name}-${index}`}
              className="suggested-folder"
            >
              <label>
                Folder name
                <input
                  type="text"
                  value={folder.name}
                  maxLength={80}
                  onChange={(event) =>
                    renameFolder(index, event.target.value)
                  }
                  disabled={busy}
                />
              </label>

              <p>{folder.documents.length} document(s)</p>

              <ul>
                {folder.documents.map((doc) => (
                  <li key={doc.id}>
                    {doc.filename} (ID: {doc.id})
                  </li>
                ))}
              </ul>
            </div>
          ))}

          <button onClick={handleConfirm} disabled={busy}>
            Confirm Organization
          </button>

          <button
            onClick={() => {
              setProposal(null);
              setError("");
              setMessage("Suggestions cancelled. No changes were applied.");
            }}
            disabled={busy}
          >
            Cancel
          </button>
        </div>
      )}

      <hr />

      <h3>Current Folders</h3>

      {folders.length === 0 ? (
        <p>No folders available.</p>
      ) : (
        folders.map((folder) => (
          <div key={folder.name} className="current-folder">
            <h4>
              {folder.name} ({folder.documents.length})
            </h4>
            <ul>
              {folder.documents.map((doc) => (
                <li key={doc.id}>
                  {doc.filename} (ID: {doc.id})
                </li>
              ))}
            </ul>
          </div>
        ))
      )}

      <hr />

      <h3>Organization History</h3>

      {history.length === 0 ? (
        <p>No organization operations yet.</p>
      ) : (
        <ul>
          {history.map((operation) => (
            <li key={operation.id}>
              Operation #{operation.id} — {operation.type} —{" "}
              {operation.status} — {operation.documents_affected} document(s)
              {latestApplied?.id === operation.id && (
                <button
                  onClick={() => handleUndo(operation.id)}
                  disabled={busy}
                >
                  Undo Latest Operation
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

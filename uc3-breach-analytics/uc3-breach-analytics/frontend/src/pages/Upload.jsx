import { useState, useRef, useEffect } from "react";
import { UploadCloud } from "lucide-react";
import { Card } from "../components";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8003";
const API_KEY = import.meta.env.VITE_API_KEY || "dev-local-key";

export default function Upload() {
  const [documents, setDocuments] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  async function loadDocuments() {
    try {
      const res = await fetch(`${API_BASE}/api/v1/documents`, { headers: { "x-api-key": API_KEY } });
      if (!res.ok) throw new Error(`Failed to load documents (${res.status})`);
      setDocuments(await res.json());
    } catch (err) { setError(err.message); }
  }

  async function uploadFiles(fileList) {
    const formData = new FormData();
    for (const file of fileList) formData.append("files", file);
    try {
      const res = await fetch(`${API_BASE}/api/v1/documents`, { method: "POST", headers: { "x-api-key": API_KEY }, body: formData });
      if (!res.ok) throw new Error(`Upload failed (${res.status})`);
      await loadDocuments();
    } catch (err) { setError(err.message); }
  }

  useEffect(() => {
    loadDocuments();
    const interval = setInterval(loadDocuments, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ width: "100%", maxWidth: 1000, display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div className={`dropzone ${dragOver ? "dragover" : ""}`}
           onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
           onDragLeave={() => setDragOver(false)}
           onDrop={(e) => { e.preventDefault(); setDragOver(false); uploadFiles(e.dataTransfer.files); }}
           onClick={() => inputRef.current?.click()}>
        <UploadCloud size={28} strokeWidth={1.5} style={{ marginBottom: "0.5rem" }} />
        <div>Drag and drop breach documents here, or click to browse</div>
        <input ref={inputRef} type="file" multiple style={{ display: "none" }} onChange={(e) => uploadFiles(e.target.files)} />
      </div>

      {error && <div style={{ color: "#e3434a", fontSize: "0.85rem" }}>{error}</div>}

      <Card interactive={false}>
        <table className="queue-table">
          <thead><tr><th>Filename</th><th>Format</th><th>Status</th><th>Quarantine Reason</th></tr></thead>
          <tbody>
            {documents.map((d) => (
              <tr key={d.id}>
                <td>{d.filename}</td>
                <td>{d.format}</td>
                <td><span className={`status-pill status-${d.status}`}>{d.status}</span></td>
                <td>{d.quarantine_reason || "—"}</td>
              </tr>
            ))}
            {documents.length === 0 && <tr><td colSpan={4} style={{ color: "var(--dfz-text-muted)" }}>No documents uploaded yet.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

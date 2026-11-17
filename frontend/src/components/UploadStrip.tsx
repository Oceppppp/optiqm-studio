import { useRef, useState } from "react";
import { downloadSampleWorkbook, exportWorkspaceOqm } from "../api/client";
import type { ModuleMeta, WorkspaceCase } from "../types";

interface Props {
  workspaceName: string;
  cases: WorkspaceCase[];
  modules: ModuleMeta[];
  selectedId: string | null;
  uploading: boolean;
  onUploadFiles: (files: File[], replace: boolean) => void;
  onImportGSheet: (url: string) => Promise<void>;
  onSelect: (id: string) => void;
}

export function UploadStrip({
  workspaceName, cases, modules, selectedId, uploading, onUploadFiles, onImportGSheet, onSelect,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [replaceMode, setReplaceMode] = useState(true);
  const [showGsheet, setShowGsheet] = useState(false);
  const [gsUrl, setGsUrl] = useState("");
  const [gsErr, setGsErr] = useState<string | null>(null);

  const prefixMap = new Map(modules.map((m) => [m.key, m.sheet_prefixes[0] || m.key.toUpperCase()]));

  const handleFiles = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    onUploadFiles(Array.from(list), replaceMode);
  };

  const submitGsheet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!gsUrl.trim()) return;
    setGsErr(null);
    try {
      await onImportGSheet(gsUrl.trim());
      setShowGsheet(false);
      setGsUrl("");
    } catch (err) {
      setGsErr(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <section
      className={`upload-strip ${dragOver ? "drag-over" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); }}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".xlsx,.xlsm,.csv,.tsv,.txt,.json,.oqm"
        style={{ display: "none" }}
        onChange={(e) => { handleFiles(e.target.files); e.target.value = ""; }}
      />

      <div className="upload-strip-top">
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button className="btn btn-sm" onClick={() => inputRef.current?.click()} disabled={uploading}>
            {uploading ? "Memproses..." : "Upload Excel / CSV / JSON"}
          </button>
          <button className="btn btn-sm" onClick={() => setShowGsheet((s) => !s)}>
            Import Google Sheets
          </button>
          <button className="btn btn-ghost btn-sm" onClick={downloadSampleWorkbook}>
            Unduh Contoh 10-Modul (.xlsx)
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => exportWorkspaceOqm(workspaceName, cases)}>
            Simpan Workspace (.oqm)
          </button>
        </div>

        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-muted)", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={!replaceMode}
            onChange={(e) => setReplaceMode(!e.target.checked)}
            style={{ accentColor: "var(--primary)" }}
          />
          Gabungkan ke kasus yang ada (jangan timpa)
        </label>
      </div>

      {showGsheet && (
        <form onSubmit={submitGsheet} style={{ marginTop: 10, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            className="input"
            style={{ flex: 1, minWidth: 260 }}
            placeholder="Tempel URL Google Sheets publik (https://docs.google.com/spreadsheets/d/.../edit)"
            value={gsUrl}
            onChange={(e) => setGsUrl(e.target.value)}
          />
          <button className="btn btn-primary btn-sm" type="submit" disabled={uploading}>Ambil Sheet</button>
          {gsErr && <span style={{ color: "var(--danger)", fontSize: 12 }}>{gsErr}</span>}
        </form>
      )}

      {cases.length > 0 && (
        <div className="sheet-chips">
          {cases.map((c) => {
            const tag = c.module ? prefixMap.get(c.module) ?? c.module : "?";
            const stCls = c.status === "valid" ? "badge-ok" : c.status === "invalid" ? "badge-err" : "badge-warn";
            return (
              <div
                key={c.id}
                className={`sheet-chip ${selectedId === c.id ? "active" : ""} ${!c.enabled ? "off" : ""}`}
                onClick={() => onSelect(c.id)}
                title={c.error ?? `${c.source} · Klik untuk edit`}
              >
                <span className="badge badge-teal mono">{tag}</span>
                <span>{c.name}</span>
                <span className={`badge ${stCls}`}>{c.status === "valid" ? "valid" : c.status === "invalid" ? "cek" : "pilih"}</span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

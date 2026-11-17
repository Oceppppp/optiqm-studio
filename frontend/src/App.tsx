import { useCallback, useEffect, useMemo, useState } from "react";
import {
  downloadReport, fetchModules, importFiles, importGSheet, runBatch, validateCase,
} from "./api/client";
import { CaseEditor } from "./components/CaseEditor";
import { ResultCard } from "./components/ResultCard";
import { Sidebar } from "./components/Sidebar";
import { UploadStrip } from "./components/UploadStrip";
import type { CaseRunResult, ModuleMeta, WorkspaceCase } from "./types";

const STARTER_KEYS = ["linear_programming", "forecasting", "project_management", "eoq"];

export default function App() {
  const [modules, setModules] = useState<ModuleMeta[]>([]);
  const [workspaceName, setWorkspaceName] = useState("Tugas_MO_MultiModul");
  const [cases, setCases] = useState<WorkspaceCase[]>([]);
  const [results, setResults] = useState<Record<string, CaseRunResult>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<"results" | "split" | "editor">("results");
  const [running, setRunning] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [bannerErr, setBannerErr] = useState<string | null>(null);
  const [lastBatchMs, setLastBatchMs] = useState<number | null>(null);

  const executeCases = useCallback(async (targetCases: WorkspaceCase[]) => {
    const active = targetCases.filter((c) => c.enabled);
    if (active.length === 0) return;
    setRunning(true);
    setBannerErr(null);
    try {
      const resp = await runBatch(active);
      setLastBatchMs(resp.duration_ms);
      setResults((prev) => {
        const next = { ...prev };
        for (const r of resp.results) next[r.id] = r;
        return next;
      });
    } catch (err) {
      setBannerErr(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const mods = await fetchModules();
        setModules(mods);
        const byKey = new Map(mods.map((m) => [m.key, m]));
        const starter: WorkspaceCase[] = [];
        for (const k of STARTER_KEYS) {
          const m = byKey.get(k);
          if (m) {
            starter.push({
              id: `init_${k}`,
              name: `${m.sheet_prefixes[0] ?? k}_Contoh`,
              source: "Starter Workspace",
              module: m.key,
              detected: true,
              enabled: true,
              status: "valid",
              error: null,
              sheet: structuredClone(m.template),
            });
          }
        }
        setCases(starter);
        setSelectedId(starter[0]?.id ?? null);
        await executeCases(starter);
      } catch (err) {
        setBannerErr(`Gagal terhubung ke engine OptiQM: ${err instanceof Error ? err.message : String(err)}`);
      }
    })();
  }, [executeCases]);

  const handleUpload = async (files: File[], replace: boolean) => {
    setUploading(true);
    setBannerErr(null);
    try {
      const imported = await importFiles(files);
      const nextCases = replace ? imported : [...cases, ...imported];
      if (replace && files[0]) setWorkspaceName(files[0].name.replace(/\.[^.]+$/, ""));
      setCases(nextCases);
      setSelectedId(imported[0]?.id ?? nextCases[0]?.id ?? null);
      if (replace) setResults({});
      await executeCases(imported);
    } catch (err) {
      setBannerErr(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  };

  const handleImportGSheet = async (url: string) => {
    setUploading(true);
    try {
      const imported = await importGSheet(url);
      setCases(imported);
      setSelectedId(imported[0]?.id ?? null);
      setResults({});
      await executeCases(imported);
    } finally {
      setUploading(false);
    }
  };

  const addModuleCase = (mod: ModuleMeta) => {
    const newCase: WorkspaceCase = {
      id: `c_${Date.now().toString(36)}`,
      name: `${mod.sheet_prefixes[0] ?? mod.key}_${cases.length + 1}`,
      source: "Manual",
      module: mod.key,
      detected: true,
      enabled: true,
      status: "valid",
      error: null,
      sheet: structuredClone(mod.template),
    };
    const next = [...cases, newCase];
    setCases(next);
    setSelectedId(newCase.id);
    setView("split");
    void executeCases([newCase]);
  };

  const updateCase = async (updated: WorkspaceCase) => {
    setCases((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
    try {
      const check = await validateCase(updated.module, updated.sheet);
      setCases((prev) => prev.map((c) => (c.id === updated.id ? { ...c, ...check } : c)));
    } catch {
      // silent during typing
    }
  };

  const selectedCase = useMemo(() => cases.find((c) => c.id === selectedId) ?? cases[0] ?? null, [cases, selectedId]);
  const activeResults = useMemo(
    () => cases.filter((c) => c.enabled).map((c) => results[c.id]).filter((r): r is CaseRunResult => Boolean(r)),
    [cases, results]
  );
  const enabledCount = cases.filter((c) => c.enabled).length;

  return (
    <div className="app-shell">
      <Sidebar
        modules={modules}
        cases={cases}
        results={results}
        selectedId={selectedCase?.id ?? null}
        onSelect={(id) => setSelectedId(id)}
        onToggle={(id) => setCases((p) => p.map((c) => (c.id === id ? { ...c, enabled: !c.enabled } : c)))}
        onRemove={(id) => setCases((p) => p.filter((c) => c.id !== id))}
        onAddModule={addModuleCase}
        onToggleAll={(en) => setCases((p) => p.map((c) => ({ ...c, enabled: en })))}
      />

      <main className="main-area">
        <header className="topbar">
          <div className="workspace-title-wrap">
            <span className="workspace-eyebrow">Workspace Multi-Modul</span>
            <input
              className="workspace-name-input"
              value={workspaceName}
              onChange={(e) => setWorkspaceName(e.target.value)}
              aria-label="Nama Workspace"
            />
          </div>

          <div className="topbar-actions">
            <div className="segmented" role="tablist">
              <button className={view === "results" ? "active" : ""} onClick={() => setView("results")}>
                Hasil Bersamaan ({activeResults.length})
              </button>
              <button className={view === "split" ? "active" : ""} onClick={() => setView("split")}>
                Split Editor + Hasil
              </button>
              <button className={view === "editor" ? "active" : ""} onClick={() => setView("editor")}>
                Editor Data
              </button>
            </div>

            <button
              className="btn btn-primary"
              disabled={running || enabledCount === 0}
              onClick={() => executeCases(cases)}
            >
              {running ? "Menjalankan..." : `Run All (${enabledCount} modul)`}
            </button>

            <button
              className="btn"
              disabled={activeResults.length === 0}
              onClick={() => void downloadReport("xlsx", workspaceName, activeResults)}
            >
              Export Excel
            </button>
            <button
              className="btn"
              disabled={activeResults.length === 0}
              onClick={() => void downloadReport("pdf", workspaceName, activeResults)}
            >
              Export PDF
            </button>
          </div>
        </header>

        <div className="workspace-scroll">
          <UploadStrip
            workspaceName={workspaceName}
            cases={cases}
            modules={modules}
            selectedId={selectedCase?.id ?? null}
            uploading={uploading}
            onUploadFiles={handleUpload}
            onImportGSheet={handleImportGSheet}
            onSelect={(id) => { setSelectedId(id); if (view === "results") setView("split"); }}
          />

          {bannerErr && <div className="err-box">{bannerErr}</div>}

          {lastBatchMs !== null && activeResults.length > 0 && (
            <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", justifyContent: "space-between" }}>
              <span>Menampilkan <b>{activeResults.length}</b> modul sekaligus (selesai dalam <span className="mono">{lastBatchMs} ms</span>)</span>
              <span>Klik kartu atau tab untuk mengedit input sebelum dijalankan ulang.</span>
            </div>
          )}

          {view === "editor" && selectedCase && (
            <CaseEditor
              item={selectedCase}
              modules={modules}
              onChange={(u) => void updateCase(u)}
              onRunSingle={(it) => void executeCases([it])}
            />
          )}

          {view === "split" && selectedCase && (
            <div className="split-pane">
              <CaseEditor
                item={selectedCase}
                modules={modules}
                onChange={(u) => void updateCase(u)}
                onRunSingle={(it) => void executeCases([it])}
              />
              {results[selectedCase.id] ? (
                <ResultCard item={results[selectedCase.id]} onInspectCase={(id) => { setSelectedId(id); setView("editor"); }} />
              ) : (
                <div className="card"><div className="card-body">Klik <b>Jalankan Kasus Ini</b> atau <b>Run All</b> untuk melihat hasil.</div></div>
              )}
            </div>
          )}

          {view === "results" && (
            <div className={`results-grid ${activeResults.length === 1 ? "single-col" : ""}`}>
              {activeResults.map((res) => (
                <ResultCard
                  key={res.id}
                  item={res}
                  onInspectCase={(id) => { setSelectedId(id); setView("split"); }}
                />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

import { useMemo, useState } from "react";
import type { CaseRunResult, ModuleMeta, WorkspaceCase } from "../types";

interface Props {
  modules: ModuleMeta[];
  cases: WorkspaceCase[];
  results: Record<string, CaseRunResult>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
  onRemove: (id: string) => void;
  onAddModule: (mod: ModuleMeta) => void;
  onToggleAll: (enabled: boolean) => void;
}

export function Sidebar({
  modules, cases, results, selectedId, onSelect, onToggle, onRemove, onAddModule, onToggleAll,
}: Props) {
  const [tab, setTab] = useState<"cases" | "catalog">("cases");
  const [query, setQuery] = useState("");

  const modName = useMemo(() => {
    const m = new Map<string, string>();
    for (const mod of modules) m.set(mod.key, mod.name);
    return m;
  }, [modules]);

  const grouped = useMemo(() => {
    const q = query.trim().toLowerCase();
    const map = new Map<string, ModuleMeta[]>();
    for (const mod of modules) {
      if (q && !mod.name.toLowerCase().includes(q) && !mod.category.toLowerCase().includes(q) && !mod.key.includes(q)) {
        continue;
      }
      const list = map.get(mod.category) ?? [];
      list.push(mod);
      map.set(mod.category, list);
    }
    return Array.from(map.entries());
  }, [modules, query]);

  const enabledCount = cases.filter((c) => c.enabled).length;

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <img src="/logo.jpg" alt="OptiQM Studio" />
        <div>
          <h1 className="brand-title">OptiQM Studio</h1>
          <div className="brand-sub">{modules.length} Modul POM-QM · Multi-Run</div>
        </div>
      </div>

      <div className="sidebar-tabs">
        <button className={`sidebar-tab ${tab === "cases" ? "active" : ""}`} onClick={() => setTab("cases")}>
          Workspace ({cases.length})
        </button>
        <button className={`sidebar-tab ${tab === "catalog" ? "active" : ""}`} onClick={() => setTab("catalog")}>
          Semua Modul ({modules.length})
        </button>
      </div>

      {tab === "cases" ? (
        <>
          <div className="sidebar-search" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12 }}>
            <span style={{ color: "var(--text-muted)" }}>{enabledCount} / {cases.length} aktif</span>
            <div style={{ display: "flex", gap: 4 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => onToggleAll(true)}>Semua</button>
              <button className="btn btn-ghost btn-sm" onClick={() => onToggleAll(false)}>Nol</button>
              <button className="btn btn-sm" onClick={() => setTab("catalog")}>+ Modul</button>
            </div>
          </div>
          <div className="sidebar-list">
            {cases.length === 0 && (
              <div style={{ padding: 14, fontSize: 12.5, color: "var(--text-muted)" }}>
                Belum ada kasus. Upload file Excel/CSV atau tambahkan modul dari tab <b>Semua Modul</b>.
              </div>
            )}
            {cases.map((c) => {
              const res = results[c.id];
              const badge = res
                ? res.status === "ok" ? <span className="badge badge-ok">OK</span> : <span className="badge badge-err">Err</span>
                : c.status === "valid"
                  ? <span className="badge badge-teal">Siap</span>
                  : <span className="badge badge-warn">!</span>;
              return (
                <div
                  key={c.id}
                  className={`case-item ${selectedId === c.id ? "selected" : ""}`}
                  onClick={() => onSelect(c.id)}
                >
                  <div className="case-item-left">
                    <input
                      type="checkbox"
                      checked={c.enabled}
                      onChange={() => onToggle(c.id)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`Aktifkan ${c.name}`}
                    />
                    <div style={{ minWidth: 0 }}>
                      <div className="case-name">{c.name}</div>
                      <div className="case-mod">{c.module ? (modName.get(c.module) ?? c.module) : "Pilih modul..."}</div>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    {badge}
                    <button
                      className="btn btn-ghost btn-sm"
                      title="Hapus kasus"
                      style={{ padding: "2px 6px" }}
                      onClick={(e) => { e.stopPropagation(); onRemove(c.id); }}
                    >
                      ×
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <>
          <div className="sidebar-search">
            <input
              className="input"
              placeholder="Cari modul (mis. LP, EOQ, PERT, Antrian)..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="sidebar-list">
            {grouped.map(([cat, mods]) => (
              <div key={cat} className="cat-group">
                <div className="cat-label">{cat}</div>
                {mods.map((m) => (
                  <div
                    key={m.key}
                    className="catalog-item"
                    title={m.description}
                    onClick={() => { onAddModule(m); setTab("cases"); }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div className="case-name">{m.name}</div>
                      <div className="case-mod">Prefix: {m.sheet_prefixes[0] ?? m.key.toUpperCase()}</div>
                    </div>
                    <button className="btn btn-sm">+ Tambah</button>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </>
      )}
    </aside>
  );
}

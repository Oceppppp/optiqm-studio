import { useState } from "react";
import { downloadModuleTemplate } from "../api/client";
import type { CellValue, ModuleMeta, SheetTable, WorkspaceCase } from "../types";

interface Props {
  item: WorkspaceCase;
  modules: ModuleMeta[];
  onChange: (updated: WorkspaceCase) => void;
  onRunSingle: (item: WorkspaceCase) => void;
}

export function CaseEditor({ item, modules, onChange, onRunSingle }: Props) {
  const mod = modules.find((m) => m.key === item.module) ?? null;
  const tableNames = Object.keys(item.sheet.tables);
  const [activeTable, setActiveTable] = useState<string>(tableNames[0] ?? "main");
  const curTableName = item.sheet.tables[activeTable] ? activeTable : (tableNames[0] ?? "");
  const curTable: SheetTable | undefined = curTableName ? item.sheet.tables[curTableName] : undefined;

  const updateParam = (key: string, val: CellValue) => {
    onChange({
      ...item,
      sheet: { ...item.sheet, params: { ...item.sheet.params, [key]: val } },
    });
  };

  const switchModule = (newKey: string) => {
    const nextMod = modules.find((m) => m.key === newKey);
    const keepTables = Object.keys(item.sheet.tables).length > 0;
    onChange({
      ...item,
      module: newKey || null,
      detected: Boolean(newKey),
      sheet: keepTables
        ? { ...item.sheet, params: { ...item.sheet.params, module: newKey } }
        : (nextMod ? structuredClone(nextMod.template) : item.sheet),
    });
  };

  const resetToTemplate = () => {
    if (!mod) return;
    onChange({ ...item, status: "valid", error: null, sheet: structuredClone(mod.template) });
  };

  const updateCell = (r: number, c: number, raw: string) => {
    if (!curTable) return;
    const trimmed = raw.trim();
    const isPartialNumber = trimmed === "-" || trimmed === "." || trimmed === "-." || /^-?\d+\.$/.test(trimmed) || /^-?\d+(\.\d+)?[eE][+-]?$/.test(trimmed);
    const parsed: CellValue = trimmed === ""
      ? null
      : (!isPartialNumber && !Number.isNaN(Number(trimmed)) ? Number(trimmed) : raw);
    const rows = curTable.rows.map((row, ri) => (ri === r ? row.map((v, ci) => (ci === c ? parsed : v)) : row));
    onChange({
      ...item,
      sheet: { ...item.sheet, tables: { ...item.sheet.tables, [curTableName]: { ...curTable, rows } } },
    });
  };

  const updateHeader = (c: number, val: string) => {
    if (!curTable) return;
    const cols = curTable.columns.map((h, ci) => (ci === c ? val : h));
    onChange({
      ...item,
      sheet: { ...item.sheet, tables: { ...item.sheet.tables, [curTableName]: { ...curTable, columns: cols } } },
    });
  };

  const addRow = () => {
    if (!curTable) return;
    const blank = curTable.columns.map(() => null);
    onChange({
      ...item,
      sheet: {
        ...item.sheet,
        tables: { ...item.sheet.tables, [curTableName]: { ...curTable, rows: [...curTable.rows, blank] } },
      },
    });
  };

  const deleteRow = (r: number) => {
    if (!curTable || curTable.rows.length <= 1) return;
    onChange({
      ...item,
      sheet: {
        ...item.sheet,
        tables: { ...item.sheet.tables, [curTableName]: { ...curTable, rows: curTable.rows.filter((_, i) => i !== r) } },
      },
    });
  };

  const addCol = () => {
    if (!curTable) return;
    const name = `Kolom${curTable.columns.length + 1}`;
    onChange({
      ...item,
      sheet: {
        ...item.sheet,
        tables: {
          ...item.sheet.tables,
          [curTableName]: { columns: [...curTable.columns, name], rows: curTable.rows.map((r) => [...r, null]) },
        },
      },
    });
  };

  return (
    <div className="card">
      <div className="card-header">
        <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
          <input
            className="input"
            style={{ maxWidth: 220, fontWeight: 700 }}
            value={item.name}
            onChange={(e) => onChange({ ...item, name: e.target.value })}
          />
          <select className="select" style={{ maxWidth: 260 }} value={item.module ?? ""} onChange={(e) => switchModule(e.target.value)}>
            <option value="">-- Pilih Modul --</option>
            {modules.map((m) => (
              <option key={m.key} value={m.key}>{m.category} — {m.name}</option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {mod && (
            <>
              <button className="btn btn-sm" onClick={() => downloadModuleTemplate(mod.key, "xlsx")}>Template .xlsx</button>
              <button className="btn btn-ghost btn-sm" onClick={resetToTemplate}>Isi Contoh Soal</button>
            </>
          )}
          <button className="btn btn-primary btn-sm" onClick={() => onRunSingle(item)} disabled={!item.module}>
            Jalankan Kasus Ini
          </button>
        </div>
      </div>

      <div className="card-body">
        {mod?.table_hint && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", background: "var(--surface-alt)", padding: "7px 10px", borderRadius: 6 }}>
            <b>Format Tabel:</b> {mod.table_hint}
          </div>
        )}

        {item.error && <div className="err-box">{item.error}</div>}

        {mod && mod.params.length > 0 && (
          <div className="params-grid">
            {mod.params.map((ps) => {
              const val = item.sheet.params[ps.name] ?? ps.default;
              const boolVal = typeof val === "boolean"
                ? val
                : !["false", "0", "no", "tidak", ""].includes(String(val ?? "").trim().toLowerCase());
              return (
                <div key={ps.name} className="param-field">
                  <label>{ps.label}</label>
                  {ps.type === "choice" ? (
                    <select className="select" value={String(val ?? ps.default)} onChange={(e) => updateParam(ps.name, e.target.value)}>
                      {ps.choices.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  ) : ps.type === "boolean" ? (
                    <select className="select" value={String(boolVal)} onChange={(e) => updateParam(ps.name, e.target.value === "true")}>
                      <option value="true">Ya (true)</option>
                      <option value="false">Tidak (false)</option>
                    </select>
                  ) : (
                    <input
                      className="input mono"
                      type={ps.type === "text" ? "text" : "number"}
                      step="any"
                      value={val === null || val === undefined ? "" : String(val)}
                      onChange={(e) => updateParam(ps.name, ps.type === "text" ? e.target.value : (e.target.value === "" ? "" : Number(e.target.value)))}
                    />
                  )}
                </div>
              );
            })}
          </div>
        )}

        {tableNames.length > 1 && (
          <div className="segmented">
            {tableNames.map((tn) => (
              <button key={tn} className={tn === curTableName ? "active" : ""} onClick={() => setActiveTable(tn)}>
                [{tn}]
              </button>
            ))}
          </div>
        )}

        {curTable && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)" }}>
                Tabel [{curTableName}] ({curTable.rows.length} baris × {curTable.columns.length} kolom)
              </span>
              <div style={{ display: "flex", gap: 6 }}>
                <button className="btn btn-sm" onClick={addRow}>+ Baris</button>
                <button className="btn btn-sm" onClick={addCol}>+ Kolom</button>
              </div>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: 28 }}>#</th>
                    {curTable.columns.map((col, ci) => (
                      <th key={ci}>
                        <input className="grid-input" style={{ fontWeight: 700 }} value={col} onChange={(e) => updateHeader(ci, e.target.value)} />
                      </th>
                    ))}
                    <th style={{ width: 32 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {curTable.rows.map((row, ri) => (
                    <tr key={ri}>
                      <td style={{ color: "var(--text-subtle)", fontSize: 11 }}>{ri + 1}</td>
                      {curTable.columns.map((_, ci) => (
                        <td key={ci}>
                          <input
                            className="grid-input mono"
                            value={row[ci] === null || row[ci] === undefined ? "" : String(row[ci])}
                            onChange={(e) => updateCell(ri, ci, e.target.value)}
                          />
                        </td>
                      ))}
                      <td>
                        <button className="btn btn-ghost btn-sm" style={{ padding: "2px 6px" }} onClick={() => deleteRow(ri)}>×</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

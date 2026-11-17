import { useState } from "react";
import type { CaseRunResult, CellValue } from "../types";
import { ChartRenderer } from "./ChartRenderer";

interface Props {
  item: CaseRunResult;
  onInspectCase: (id: string) => void;
}

function formatCell(v: CellValue): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return v.toLocaleString("id-ID");
    return v.toLocaleString("id-ID", { maximumFractionDigits: 4 });
  }
  return String(v);
}

export function ResultCard({ item, onInspectCase }: Props) {
  const [showSteps, setShowSteps] = useState(false);
  const res = item.result;

  return (
    <article className="card">
      <div className="card-header">
        <div style={{ minWidth: 0 }}>
          <h3 className="card-title">{item.name}</h3>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
            {item.module_name ?? item.module} · <span className="mono">{item.duration_ms} ms</span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className={`badge ${item.status === "ok" ? "badge-ok" : "badge-err"}`}>
            {item.status === "ok" ? "Sukses" : "Error"}
          </span>
          <button className="btn btn-ghost btn-sm" onClick={() => onInspectCase(item.id)}>Edit Data</button>
        </div>
      </div>

      <div className="card-body">
        {item.status === "error" || !res ? (
          <div className="err-box">{item.error ?? "Gagal menyelesaikan kasus."}</div>
        ) : (
          <>
            {res.warnings.length > 0 && (
              <div className="warn-box">{res.warnings.join(" ")}</div>
            )}

            {res.summary.length > 0 && (
              <div className="metrics-row">
                {res.summary.map((m) => (
                  <div key={m.label} className={`metric-box ${m.highlight ? "highlight" : ""}`}>
                    <div className="metric-label">{m.label}</div>
                    <div className="metric-val mono">
                      {formatCell(m.value)} {m.unit ? <span style={{ fontSize: 11, fontWeight: 500 }}>{m.unit}</span> : null}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {res.interpretation && <div className="interpretation">{res.interpretation}</div>}

            {res.charts.map((ch, idx) => <ChartRenderer key={idx} chart={ch} />)}

            {res.tables.map((tbl, idx) => (
              <div key={idx}>
                <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 5 }}>{tbl.title}</div>
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>{tbl.columns.map((c, ci) => <th key={ci}>{c}</th>)}</tr>
                    </thead>
                    <tbody>
                      {tbl.rows.map((row, ri) => (
                        <tr key={ri}>
                          {row.map((val, ci) => (
                            <td key={ci} className={typeof val === "number" ? "num" : ""}>{formatCell(val)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {tbl.note && <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 4 }}>{tbl.note}</div>}
              </div>
            ))}

            {res.steps.length > 0 && (
              <div>
                <button className="btn btn-sm" onClick={() => setShowSteps((s) => !s)}>
                  {showSteps ? "Sembunyikan" : "Lihat"} Langkah Perhitungan ({res.steps.length})
                </button>
                {showSteps && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10 }}>
                    {res.steps.map((st, idx) => (
                      <div key={idx}>
                        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>{st.title}</div>
                        <div className="table-wrap">
                          <table className="data-table">
                            <thead><tr>{st.columns.map((c, ci) => <th key={ci}>{c}</th>)}</tr></thead>
                            <tbody>
                              {st.rows.map((row, ri) => (
                                <tr key={ri}>
                                  {row.map((val, ci) => <td key={ci} className={typeof val === "number" ? "num" : ""}>{formatCell(val)}</td>)}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {st.note && <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 3 }}>{st.note}</div>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </article>
  );
}

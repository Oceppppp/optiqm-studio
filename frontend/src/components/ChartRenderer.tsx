import type { ChartSpec } from "../types";

const PALETTE = ["#0f5257", "#d97706", "#2563eb", "#059669", "#dc2626", "#7c3aed"];

interface Series {
  name: string;
  data: (number | null)[];
}

export function ChartRenderer({ chart }: { chart: ChartSpec }) {
  const d = chart.data;
  return (
    <div className="chart-box">
      <div className="chart-title">{chart.title}</div>
      {chart.kind === "lp_region" && <LpRegionChart data={d} />}
      {chart.kind === "network" && <NetworkChart data={d} />}
      {chart.kind === "gantt" && <GanttChart data={d} />}
      {chart.kind === "scatter" && <ScatterChart data={d} />}
      {(chart.kind === "line" || chart.kind === "area") && <LineChart data={d} />}
      {chart.kind === "bar" && <BarChart data={d} />}
    </div>
  );
}

function fmt(n: number): string {
  if (Math.abs(n) >= 1e5 || (Math.abs(n) > 0 && Math.abs(n) < 0.01)) return n.toExponential(1);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function LineChart({ data }: { data: Record<string, unknown> }) {
  const xs = (data.x as string[]) ?? [];
  const series = (data.series as Series[]) ?? [];
  const allVals = series.flatMap((s) => s.data.filter((v): v is number => typeof v === "number"));
  if (xs.length === 0 || allVals.length === 0) return null;

  const W = 500, H = 220, L = 48, R = 16, T = 14, B = 32;
  const minY = Math.min(0, ...allVals);
  const maxY = Math.max(...allVals, minY + 1);
  const px = (i: number) => L + (xs.length === 1 ? (W - L - R) / 2 : (i / (xs.length - 1)) * (W - L - R));
  const py = (v: number) => H - B - ((v - minY) / (maxY - minY)) * (H - T - B);

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const v = minY + t * (maxY - minY);
          const y = py(v);
          return (
            <g key={t}>
              <line x1={L} y1={y} x2={W - R} y2={y} stroke="#ece8df" strokeWidth={1} />
              <text x={L - 6} y={y + 3} textAnchor="end" fontSize={10} fill="#6b7280">{fmt(v)}</text>
            </g>
          );
        })}
        {xs.map((lbl, i) => {
          const step = Math.max(1, Math.ceil(xs.length / 8));
          if (i % step !== 0 && i !== xs.length - 1) return null;
          return <text key={i} x={px(i)} y={H - 12} textAnchor="middle" fontSize={10} fill="#6b7280">{String(lbl).slice(0, 8)}</text>;
        })}
        {series.map((s, si) => {
          const col = PALETTE[si % PALETTE.length];
          const pts: string[] = [];
          s.data.forEach((v, i) => {
            if (typeof v === "number") pts.push(`${pts.length === 0 ? "M" : "L"} ${px(i)} ${py(v)}`);
          });
          return (
            <g key={s.name}>
              <path d={pts.join(" ")} fill="none" stroke={col} strokeWidth={2} />
              {s.data.map((v, i) => typeof v === "number" && xs.length <= 28
                ? <circle key={i} cx={px(i)} cy={py(v)} r={2.8} fill={col}><title>{`${s.name} (${xs[i]}): ${v}`}</title></circle>
                : null)}
            </g>
          );
        })}
      </svg>
      <Legend items={series.map((s, i) => ({ name: s.name, color: PALETTE[i % PALETTE.length] }))} />
    </div>
  );
}

function BarChart({ data }: { data: Record<string, unknown> }) {
  const xs = (data.x as string[]) ?? [];
  const series = (data.series as Series[]) ?? [];
  const allVals = series.flatMap((s) => s.data.filter((v): v is number => typeof v === "number"));
  if (xs.length === 0 || allVals.length === 0) return null;

  const W = 500, H = 220, L = 48, R = 16, T = 14, B = 36;
  const minY = Math.min(0, ...allVals);
  const maxY = Math.max(...allVals, minY + 1);
  const py = (v: number) => H - B - ((v - minY) / (maxY - minY)) * (H - T - B);
  const y0 = py(0);
  const slot = (W - L - R) / xs.length;
  const bw = Math.max(4, Math.min(28, (slot * 0.72) / Math.max(1, series.length)));

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {[0, 0.5, 1].map((t) => {
          const v = minY + t * (maxY - minY);
          const y = py(v);
          return (
            <g key={t}>
              <line x1={L} y1={y} x2={W - R} y2={y} stroke="#ece8df" strokeWidth={1} />
              <text x={L - 6} y={y + 3} textAnchor="end" fontSize={10} fill="#6b7280">{fmt(v)}</text>
            </g>
          );
        })}
        {xs.map((lbl, i) => {
          const cx = L + slot * (i + 0.5);
          const totalW = series.length * bw;
          return (
            <g key={i}>
              {series.map((s, si) => {
                const v = s.data[i];
                if (typeof v !== "number") return null;
                const yv = py(v);
                const x = cx - totalW / 2 + si * bw;
                return (
                  <rect
                    key={si} x={x} y={Math.min(yv, y0)} width={bw - 1} height={Math.max(1, Math.abs(y0 - yv))}
                    rx={2} fill={PALETTE[si % PALETTE.length]}
                  >
                    <title>{`${s.name} — ${lbl}: ${v}`}</title>
                  </rect>
                );
              })}
              <text x={cx} y={H - 14} textAnchor="middle" fontSize={9.5} fill="#6b7280">{String(lbl).slice(0, 10)}</text>
            </g>
          );
        })}
      </svg>
      <Legend items={series.map((s, i) => ({ name: s.name, color: PALETTE[i % PALETTE.length] }))} />
    </div>
  );
}

function ScatterChart({ data }: { data: Record<string, unknown> }) {
  const series = (data.series as { name: string; points: [number, number][] }[]) ?? [];
  const pts = series.flatMap((s) => s.points);
  if (pts.length === 0) return null;

  const W = 500, H = 220, L = 46, R = 16, T = 16, B = 32;
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const minX = Math.min(...xs) - 10, maxX = Math.max(...xs) + 10;
  const minY = Math.min(...ys) - 10, maxY = Math.max(...ys) + 10;
  const px = (x: number) => L + ((x - minX) / Math.max(1, maxX - minX)) * (W - L - R);
  const py = (y: number) => H - B - ((y - minY) / Math.max(1, maxY - minY)) * (H - T - B);

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        <line x1={L} y1={H - B} x2={W - R} y2={H - B} stroke="#cbc4b6" />
        <line x1={L} y1={T} x2={L} y2={H - B} stroke="#cbc4b6" />
        {series.map((s, si) =>
          s.points.map(([x, y], pi) => (
            <circle key={`${si}-${pi}`} cx={px(x)} cy={py(y)} r={si === 1 ? 7 : 5} fill={PALETTE[si % PALETTE.length]}>
              <title>{`${s.name}: (${x.toFixed(2)}, ${y.toFixed(2)})`}</title>
            </circle>
          ))
        )}
      </svg>
      <Legend items={series.map((s, i) => ({ name: s.name, color: PALETTE[i % PALETTE.length] }))} />
    </div>
  );
}

function LpRegionChart({ data }: { data: Record<string, unknown> }) {
  const lines = (data.lines as { name: string; points: [number, number][] }[]) ?? [];
  const poly = (data.polygon as [number, number][]) ?? [];
  const opt = (data.optimum as [number, number] | null) ?? null;
  const xMax = Number(data.x_max || 10), yMax = Number(data.y_max || 10);

  const W = 500, H = 240, L = 44, R = 16, T = 14, B = 32;
  const px = (x: number) => L + (x / xMax) * (W - L - R);
  const py = (y: number) => H - B - (y / yMax) * (H - T - B);
  const polyAttr = poly.map(([x, y]) => `${px(x)},${py(y)}`).join(" ");

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        <defs>
          <clipPath id="lp-clip"><rect x={L} y={T} width={W - L - R} height={H - T - B} /></clipPath>
        </defs>
        <line x1={L} y1={H - B} x2={W - R} y2={H - B} stroke="#9ca3af" />
        <line x1={L} y1={T} x2={L} y2={H - B} stroke="#9ca3af" />
        <text x={W - R} y={H - 10} textAnchor="end" fontSize={10} fill="#4b5563">{String(data.x_label ?? "X1")}</text>
        <text x={L + 4} y={T + 10} fontSize={10} fill="#4b5563">{String(data.y_label ?? "X2")}</text>
        <g clipPath="url(#lp-clip)">
          {poly.length >= 3 && <polygon points={polyAttr} fill="#0f5257" fillOpacity={0.18} stroke="#0f5257" strokeWidth={1.5} />}
          {lines.map((ln, i) => (
            <line
              key={i} x1={px(ln.points[0][0])} y1={py(ln.points[0][1])}
              x2={px(ln.points[1][0])} y2={py(ln.points[1][1])}
              stroke={PALETTE[(i + 1) % PALETTE.length]} strokeWidth={1.6} strokeDasharray={i > 0 ? "4 2" : undefined}
            >
              <title>{ln.name}</title>
            </line>
          ))}
          {opt && (
            <g>
              <circle cx={px(opt[0])} cy={py(opt[1])} r={6} fill="#d97706" stroke="#fff" strokeWidth={2} />
              <text x={px(opt[0]) + 8} y={py(opt[1]) - 6} fontSize={10.5} fontWeight={700} fill="#92400e">
                Optimal ({fmt(opt[0])}, {fmt(opt[1])})
              </text>
            </g>
          )}
        </g>
      </svg>
    </div>
  );
}

function NetworkChart({ data }: { data: Record<string, unknown> }) {
  const nodes = (data.nodes as { id: string; label: string; highlight: boolean }[]) ?? [];
  const edges = (data.edges as { source: string; target: string; label: string; highlight: boolean }[]) ?? [];
  const directed = Boolean(data.directed);
  if (nodes.length === 0) return null;

  // Hitung level sederhana untuk tata letak kiri -> kanan
  const level = new Map<string, number>();
  nodes.forEach((n) => level.set(n.id, 0));
  for (let pass = 0; pass < nodes.length; pass++) {
    for (const e of edges) {
      const lu = level.get(e.source) ?? 0;
      const lv = level.get(e.target) ?? 0;
      if (lv <= lu) level.set(e.target, lu + 1);
    }
  }
  const byLvl = new Map<number, typeof nodes>();
  for (const n of nodes) {
    const l = level.get(n.id) ?? 0;
    const arr = byLvl.get(l) ?? [];
    arr.push(n);
    byLvl.set(l, arr);
  }
  const maxLvl = Math.max(...Array.from(byLvl.keys()), 1);
  const W = 540, H = Math.max(200, Math.max(...Array.from(byLvl.values()).map((a) => a.length)) * 54);
  const pos = new Map<string, { x: number; y: number }>();
  for (const [l, arr] of byLvl.entries()) {
    const x = 52 + (l / maxLvl) * (W - 104);
    arr.forEach((n, idx) => {
      const y = ((idx + 1) / (arr.length + 1)) * H;
      pos.set(n.id, { x, y });
    });
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
      <defs>
        <marker id="arr-normal" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="#9ca3af" />
        </marker>
        <marker id="arr-hi" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="#d97706" />
        </marker>
      </defs>
      {edges.map((e, i) => {
        const a = pos.get(e.source), b = pos.get(e.target);
        if (!a || !b) return null;
        const dx = b.x - a.x, dy = b.y - a.y, dist = Math.hypot(dx, dy) || 1;
        const pad = 18;
        const x1 = a.x + (dx / dist) * pad, y1 = a.y + (dy / dist) * pad;
        const x2 = b.x - (dx / dist) * pad, y2 = b.y - (dy / dist) * pad;
        return (
          <g key={i}>
            <line
              x1={x1} y1={y1} x2={x2} y2={y2}
              stroke={e.highlight ? "#d97706" : "#b8b3a8"} strokeWidth={e.highlight ? 2.5 : 1.3}
              markerEnd={directed ? (e.highlight ? "url(#arr-hi)" : "url(#arr-normal)") : undefined}
            />
            {e.label && (
              <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 4} textAnchor="middle" fontSize={9.5} fontWeight={600}
                    fill={e.highlight ? "#92400e" : "#4b5563"}>
                {e.label}
              </text>
            )}
          </g>
        );
      })}
      {nodes.map((n) => {
        const p = pos.get(n.id)!;
        return (
          <g key={n.id}>
            <circle cx={p.x} cy={p.y} r={16} fill={n.highlight ? "#0f5257" : "#f6f4ef"}
                    stroke={n.highlight ? "#d97706" : "#8b928e"} strokeWidth={n.highlight ? 2.4 : 1.3} />
            <text x={p.x} y={p.y + 3.5} textAnchor="middle" fontSize={9.5} fontWeight={700}
                  fill={n.highlight ? "#ffffff" : "#1c2422"}>
              {n.label.slice(0, 8)}
            </text>
            <title>{n.label}</title>
          </g>
        );
      })}
    </svg>
  );
}

function GanttChart({ data }: { data: Record<string, unknown> }) {
  const tasks = (data.tasks as { name: string; start: number; end: number; highlight: boolean }[]) ?? [];
  if (tasks.length === 0) return null;
  const maxT = Math.max(...tasks.map((t) => t.end), 1);
  const W = 500, rowH = 22, L = 86, R = 16, T = 10, B = 24;
  const H = T + tasks.length * rowH + B;
  const px = (t: number) => L + (t / maxT) * (W - L - R);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
      {tasks.map((t, i) => {
        const y = T + i * rowH;
        const x = px(t.start), w = Math.max(4, px(t.end) - x);
        return (
          <g key={i}>
            <text x={L - 6} y={y + 13} textAnchor="end" fontSize={10.5} fill="#374151">{t.name.slice(0, 11)}</text>
            <rect x={x} y={y + 3} width={w} height={14} rx={3} fill={t.highlight ? "#d97706" : "#0f5257"}>
              <title>{`${t.name}: ${t.start} → ${t.end}`}</title>
            </rect>
            <text x={x + w + 4} y={y + 13} fontSize={9.5} fill="#6b7280">{`${fmt(t.start)}–${fmt(t.end)}`}</text>
          </g>
        );
      })}
      <line x1={L} y1={H - B + 4} x2={W - R} y2={H - B + 4} stroke="#cbc4b6" />
      <text x={L} y={H - 6} fontSize={9.5} fill="#6b7280">0</text>
      <text x={W - R} y={H - 6} textAnchor="end" fontSize={9.5} fill="#6b7280">{fmt(maxT)}</text>
    </svg>
  );
}

function Legend({ items }: { items: { name: string; color: string }[] }) {
  if (items.length <= 1) return null;
  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 6, fontSize: 11.5, color: "var(--text-muted)" }}>
      {items.map((it) => (
        <span key={it.name} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: it.color, display: "inline-block" }} />
          {it.name}
        </span>
      ))}
    </div>
  );
}

import type { BatchRunResponse, CaseRunResult, ModuleMeta, SheetDataDict, WorkspaceCase } from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "");

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  const contentType = res.headers.get("content-type") ?? "";
  const text = await res.text();
  const isHtml = !contentType.includes("application/json") && text.trimStart().startsWith("<");

  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    if (!isHtml) {
      try {
        const body = JSON.parse(text);
        if (body?.detail) msg = String(body.detail);
      } catch {
        // keep status
      }
    } else if (!API_BASE) {
      msg =
        "Backend API belum terhubung di /api. Jika di Vercel, deploy dari root repo dengan Framework Preset 'Services' (vercel.json). Jika frontend terpisah (mis. Netlify), deploy backend/ lalu isi VITE_API_BASE_URL.";
    } else {
      msg = `Backend (${API_BASE}) mengembalikan HTML (HTTP ${res.status}), bukan JSON. Pastikan URL VITE_API_BASE_URL benar dan server backend aktif.`;
    }
    throw new Error(msg);
  }

  if (isHtml) {
    if (!API_BASE) {
      throw new Error(
        "Backend API belum terhubung di /api. Jika di Vercel, deploy dari root repo dengan Framework Preset 'Services' (vercel.json). Jika frontend terpisah (mis. Netlify), deploy backend/ lalu isi VITE_API_BASE_URL dan redeploy."
      );
    }
    throw new Error(
      `Respons dari ${API_BASE} berupa HTML, bukan JSON. Pastikan URL VITE_API_BASE_URL mengarah ke server backend FastAPI yang aktif.`
    );
  }

  return JSON.parse(text) as T;
}

export async function fetchModules(): Promise<ModuleMeta[]> {
  const data = await jsonOrThrow<{ modules: ModuleMeta[] }>(await fetch(apiUrl("/api/modules")));
  return data.modules;
}

export async function importFiles(files: File[]): Promise<WorkspaceCase[]> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const data = await jsonOrThrow<{ cases: WorkspaceCase[] }>(
    await fetch(apiUrl("/api/workspace/import"), { method: "POST", body: fd })
  );
  return data.cases;
}

export async function importGSheet(url: string): Promise<WorkspaceCase[]> {
  const data = await jsonOrThrow<{ cases: WorkspaceCase[] }>(
    await fetch(apiUrl("/api/workspace/import-gsheet"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    })
  );
  return data.cases;
}

export async function validateCase(module: string | null, sheet: SheetDataDict): Promise<{ status: "valid" | "invalid" | "needs_module"; error: string | null }> {
  return jsonOrThrow(
    await fetch(apiUrl("/api/workspace/validate"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module, sheet }),
    })
  );
}

export async function runBatch(cases: WorkspaceCase[]): Promise<BatchRunResponse> {
  return jsonOrThrow(
    await fetch(apiUrl("/api/batch/run"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cases }),
    })
  );
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function downloadReport(format: "xlsx" | "pdf", workspaceName: string, items: CaseRunResult[]) {
  const res = await fetch(apiUrl(`/api/report/${format}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspace_name: workspaceName, items }),
  });
  if (!res.ok) throw new Error(`Gagal membuat laporan ${format.toUpperCase()}`);
  const blob = await res.blob();
  const safe = workspaceName.replace(/[^a-zA-Z0-9_-]+/g, "_") || "OptiQM";
  triggerDownload(blob, `${safe}_Laporan.${format}`);
}

export function downloadSampleWorkbook() {
  window.location.href = apiUrl("/api/templates/sample-workbook.xlsx");
}

export function downloadModuleTemplate(key: string, format: "xlsx" | "csv" = "xlsx") {
  window.location.href = apiUrl(`/api/modules/${key}/template?format=${format}`);
}

export function exportWorkspaceOqm(name: string, cases: WorkspaceCase[]) {
  const payload = {
    app: "OptiQM Studio",
    version: "1.0.0",
    workspace: name,
    cases: cases.map((c) => ({ name: c.name, module: c.module, enabled: c.enabled, params: c.sheet.params, tables: c.sheet.tables })),
  };
  triggerDownload(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }), `${name || "workspace"}.oqm`);
}

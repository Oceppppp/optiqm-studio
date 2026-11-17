export interface ParamSpec {
  name: string;
  label: string;
  type: "number" | "integer" | "text" | "choice" | "boolean";
  default: string | number | boolean;
  choices: string[];
  help: string;
  required: boolean;
}

export type CellValue = string | number | boolean | null;

export interface SheetTable {
  columns: string[];
  rows: CellValue[][];
}

export interface SheetDataDict {
  params: Record<string, CellValue>;
  tables: Record<string, SheetTable>;
}

export interface ModuleMeta {
  key: string;
  name: string;
  category: string;
  description: string;
  sheet_prefixes: string[];
  params: ParamSpec[];
  table_hint: string;
  template: SheetDataDict;
}

export interface WorkspaceCase {
  id: string;
  name: string;
  source: string;
  module: string | null;
  detected: boolean;
  enabled: boolean;
  status: "valid" | "invalid" | "needs_module";
  error: string | null;
  sheet: SheetDataDict;
}

export interface ResultMetric {
  label: string;
  value: CellValue;
  unit: string;
  highlight: boolean;
}

export interface ResultTable {
  title: string;
  columns: string[];
  rows: CellValue[][];
  note?: string;
}

export interface ChartSpec {
  title: string;
  kind: "line" | "bar" | "area" | "scatter" | "lp_region" | "network" | "gantt";
  data: Record<string, unknown>;
}

export interface ModuleResultDict {
  summary: ResultMetric[];
  tables: ResultTable[];
  charts: ChartSpec[];
  steps: ResultTable[];
  warnings: string[];
  interpretation: string;
}

export interface CaseRunResult {
  id: string;
  name: string;
  module: string | null;
  module_name?: string;
  category?: string;
  status: "ok" | "error";
  error: string | null;
  duration_ms: number;
  result: ModuleResultDict | null;
}

export interface BatchRunResponse {
  total: number;
  succeeded: number;
  failed: number;
  duration_ms: number;
  results: CaseRunResult[];
}

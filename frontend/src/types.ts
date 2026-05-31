export type ViewKey = "engine" | "matrix" | "scorecard" | "studio";

export type PhaseStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | "not_implemented";

export interface Phase {
  phase: number;
  name: string;
  status: PhaseStatus;
}

export interface RunEvent {
  seq: number;
  ts: number;
  type:
    | "log"
    | "metric"
    | "phase"
    | "run"
    | "note"
    | "telemetry"
    | "targets_ready"
    | "synced";
  // log
  level?: string;
  logger?: string;
  message?: string;
  // metric
  key?: string;
  value?: number;
  label?: string;
  unit?: string;
  // phase
  phase?: number;
  name?: string;
  status?: string;
  // note
  title?: string;
  data?: any;
  // run
  error?: string;
  missing_required?: string[];
  through_phase?: number;
  running?: boolean;
  done?: boolean;
  // telemetry fields are merged in directly
  ram_used_gb?: number;
  ram_total_gb?: number;
  ram_pct?: number;
  vram_used_mb?: number;
  vram_total_mb?: number;
  vram_pct?: number;
  cpu_pct?: number;
}

export interface RunSummary {
  id: string;
  disease_name: string;
  status: string;
  current_phase: number;
  intent_mode: string;
  efo_id?: string;
  created_at: string;
  running?: boolean;
}

export interface Telemetry {
  ram_used_gb?: number | null;
  ram_total_gb?: number | null;
  ram_pct?: number | null;
  vram_used_mb?: number | null;
  vram_total_mb?: number | null;
  vram_pct?: number | null;
  cpu_pct?: number | null;
}

export interface ShapItem {
  feature: string;
  value: number;
}

export interface EvidenceTrail {
  xgb_probability?: number;
  pu_percentile?: number;
  dorothea_activity?: number;
  is_master_regulator?: boolean;
  regulon_size?: number;
  dorothea_confidence?: string;
  shap_top?: ShapItem[];
  essentiality?: number;
  selective_fraction?: number;
  expression?: number;
  tractability?: number;
  genetic?: number;
  ppi_eigenvector?: number;
}

export interface Target {
  rank: number;
  symbol: string;
  ensembl_id?: string;
  aggregate_score: number;
  validation_score?: number | null;
  tdl?: string;
  modality_primary?: string;
  modality_secondary?: string | null;
  evidence_trail: EvidenceTrail;
}

export interface Metric {
  key: string;
  value: number;
  label: string;
  unit: string;
}

export interface LogLine {
  seq: number;
  ts: number;
  level: string;
  logger: string;
  message: string;
}

export type RunState = "idle" | "running" | "completed" | "failed";

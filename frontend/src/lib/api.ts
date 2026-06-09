/**
 * Typed HTTP client for the FastAPI backend.
 * All functions throw on non-2xx responses.
 */

const BASE = '/api';

async function _get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} → ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function _post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail?.detail ?? `POST ${path} → ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Response types ────────────────────────────────────────────────────────────

export interface RunSummary {
  id: string;
  disease_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  current_phase: number;
  intent_mode: string;
  efo_id: string | null;
  cost_usd: number | null;
  created_at: string;
  running: boolean;
  module_run: boolean;
  module_phase: number | null;
}

export interface PhaseResult {
  phase: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface RunDetail {
  run: RunSummary & { config: Record<string, unknown> };
  phases: PhaseResult[];
  running: boolean;
}

export interface ApiTarget {
  rank: number;
  symbol: string;
  ensembl_id: string;
  aggregate_score: number;
  validation_score: number | null;
  tdl: string;
  modality_primary: string | null;
  modality_secondary: string | null;
  seeded: boolean;
  evidence_trail: Record<string, unknown>;
}

export interface ApiCandidate {
  id: string;
  target_id: string;
  kind: 'repurposing' | 'sm' | 'biologic';
  identifier: string;
  smiles: string | null;
  sequence: string | null;
  combined_score: number;
  subscores: Record<string, unknown>;
  created_at: string;
}

export interface ApiDecision {
  phase: number;
  gate: string;
  llm_provider: string;
  llm_model: string;
  decision_json: Record<string, unknown>;
  human_override: Record<string, unknown> | null;
  created_at: string;
}

export interface ComputeEntry {
  phase: number;
  step: string;
  service: string;
  cost_usd: number;
  wall_time_s: number;
  created_at: string;
}

export interface Artifact {
  run_id: string;
  run_name: string;
  phase: number;
  artifact_type: string;
  finished_at: string;
}

export interface Telemetry {
  ts: number;
  ram_used_gb: number | null;
  ram_total_gb: number | null;
  ram_pct: number | null;
  vram_used_mb: number | null;
  vram_total_mb: number | null;
  vram_pct: number | null;
  cpu_pct: number | null;
}

// ── API functions ─────────────────────────────────────────────────────────────

export const api = {
  health: () => _get<{ status: string; supabase: boolean; phases_implemented: number[] }>('/health'),

  telemetry: () => _get<Telemetry>('/system/telemetry'),

  genes: (q: string, limit = 20) =>
    _get<{ query: string; results: string[] }>(`/genes?q=${encodeURIComponent(q)}&limit=${limit}`),

  // E2E runs
  listRuns: () => _get<{ runs: RunSummary[]; phase_names: Record<number, string> }>('/runs'),

  getRun: (runId: string) => _get<RunDetail>(`/runs/${runId}`),

  createRun: (body: {
    disease: string;
    disease_efo_id: string;
    intent_mode?: string;
    known_positives: string[];
    seed_smiles?: string[];
    exclude_targets?: string[];
    tissue_of_interest?: string;
    indication_type?: string;
    provider?: string;
    target_count_max?: number;
    pu_n_bags?: number;
    through_phase?: number;
  }) => _post<{ run_id: string; through_phase: number }>('/runs', body),

  getTargets: (runId: string) =>
    _get<{ targets: ApiTarget[] }>(`/runs/${runId}/targets`),

  getCandidates: (runId: string) =>
    _get<{ candidates: ApiCandidate[] }>(`/runs/${runId}/candidates`),

  getDecisions: (runId: string) =>
    _get<{ decisions: ApiDecision[] }>(`/runs/${runId}/decisions`),

  getCompute: (runId: string) =>
    _get<{ compute: ComputeEntry[] }>(`/runs/${runId}/compute`),

  getEvents: (runId: string) =>
    _get<{ events: unknown[]; running: boolean; done: boolean }>(`/runs/${runId}/events`),

  // Module runs
  createModuleRun: (body: {
    phase_num: number;
    run_name?: string;
    artifact_inputs?: Record<string, {
      source: 'upload' | 'run' | 'manual';
      source_run_id?: string;
      source_phase?: number;
      data?: Record<string, unknown>;
    }>;
    params?: Record<string, unknown>;
  }) => _post<{ run_id: string; phase: number; inputs_resolved: string[] }>('/module-runs', body),

  getModuleRun: (runId: string) => _get<RunDetail>(`/module-runs/${runId}`),

  // Artifacts
  listArtifacts: (artifactType?: string) =>
    _get<{ artifacts: Artifact[] }>(
      `/artifacts${artifactType ? `?artifact_type=${encodeURIComponent(artifactType)}` : ''}`
    ),
};

// ── WebSocket helper ──────────────────────────────────────────────────────────

export type StreamEvent = {
  seq: number;
  ts: number;
  type: 'run' | 'phase' | 'step' | 'note' | 'log' | 'metric' | 'telemetry' | 'targets_ready' | 'synced';
  [key: string]: unknown;
};

/**
 * Open a WebSocket to the run event stream.
 * Returns a cleanup function. Reconnects automatically on close (up to maxRetries).
 */
export function openRunStream(
  runId: string,
  onEvent: (evt: StreamEvent) => void,
  maxRetries = 5,
): () => void {
  let ws: WebSocket | null = null;
  let retries = 0;
  let stopped = false;

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/api/runs/${runId}/stream`);

    ws.onmessage = (e) => {
      try {
        onEvent(JSON.parse(e.data) as StreamEvent);
      } catch {
        // malformed event — ignore
      }
    };

    ws.onclose = () => {
      if (stopped) return;
      if (retries < maxRetries) {
        retries++;
        setTimeout(connect, Math.min(1000 * retries, 10000));
      }
    };
  }

  connect();

  return () => {
    stopped = true;
    ws?.close();
  };
}

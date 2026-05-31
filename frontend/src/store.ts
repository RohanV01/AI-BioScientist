import { create } from "zustand";
import { api, openStream } from "./lib/api";
import type {
  LogLine,
  Metric,
  Phase,
  RunEvent,
  RunState,
  RunSummary,
  Target,
  Telemetry,
  ViewKey,
} from "./types";

const PHASE_NAMES: Record<number, string> = {
  0: "Setup & Health",
  1: "Target ID",
  2: "Target Validation",
  3: "Modality Selection",
  4: "Repurposing",
  5: "De Novo Small Molecule",
  6: "De Novo Biologic",
  7: "Multi-Parameter Optimization",
  8: "Validation Gate",
  9: "Packaging",
};
const IMPLEMENTED_MAX = 3;
const LOG_CAP = 4000;

function defaultPhases(): Phase[] {
  return Array.from({ length: 10 }, (_, p) => ({
    phase: p,
    name: PHASE_NAMES[p],
    status: p > IMPLEMENTED_MAX ? "not_implemented" : "pending",
  }));
}

export interface StartPayload {
  disease: string;
  disease_efo_id?: string;
  intent_mode: string;
  known_positives: string[];
  exclude_targets: string[];
  tissue_of_interest: string;
  indication_type: string;
  provider: string;
  target_count_max: number;
  pu_n_bags: number;
  through_phase: number;
}

interface StoreState {
  view: ViewKey;
  runs: RunSummary[];
  activeRunId: string | null;
  activeDisease: string;
  phases: Phase[];
  logs: LogLine[];
  metrics: Record<string, Metric>;
  notes: RunEvent[];
  telemetry: Telemetry;
  runState: RunState;
  runError: string | null;
  missingRequired: string[];
  throughPhase: number;
  targets: Target[];
  selectedRank: number | null;
  streamOpen: boolean;
  starting: boolean;

  _disconnect: (() => void) | null;

  setView: (v: ViewKey) => void;
  setSelected: (rank: number | null) => void;
  loadRuns: () => Promise<void>;
  startRun: (p: StartPayload) => Promise<void>;
  openRun: (id: string, fresh?: boolean) => Promise<void>;
  fetchTargets: (id?: string) => Promise<void>;
  startTelemetryPoll: () => () => void;
  _applyBatch: (events: RunEvent[]) => void;
}

export const useStore = create<StoreState>((set, get) => ({
  view: "engine",
  runs: [],
  activeRunId: null,
  activeDisease: "",
  phases: defaultPhases(),
  logs: [],
  metrics: {},
  notes: [],
  telemetry: {},
  runState: "idle",
  runError: null,
  missingRequired: [],
  throughPhase: 1,
  targets: [],
  selectedRank: null,
  streamOpen: false,
  starting: false,
  _disconnect: null,

  setView: (v) => set({ view: v }),
  setSelected: (rank) => set({ selectedRank: rank }),

  loadRuns: async () => {
    try {
      const { runs } = await api.get<{ runs: RunSummary[] }>("/runs");
      set({ runs });
    } catch {
      /* surfaced elsewhere */
    }
  },

  startRun: async (p) => {
    set({ starting: true, runError: null, missingRequired: [] });
    try {
      const res = await api.post<{ run_id: string; through_phase: number }>("/runs", p);
      await get().openRun(res.run_id, true);
      set({ activeDisease: p.disease, throughPhase: res.through_phase });
      get().loadRuns();
    } catch (e: any) {
      set({ runError: e?.message || "Failed to start run" });
    } finally {
      set({ starting: false });
    }
  },

  openRun: async (id, fresh = false) => {
    const prev = get()._disconnect;
    if (prev) prev();

    // reset live state for the newly-focused run
    set({
      activeRunId: id,
      logs: [],
      metrics: {},
      notes: [],
      phases: defaultPhases(),
      targets: [],
      selectedRank: null,
      runState: fresh ? "running" : "idle",
      runError: null,
      missingRequired: [],
      view: fresh ? "matrix" : get().view,
    });

    // hydrate header/phases/targets from REST (for historical runs)
    if (!fresh) {
      try {
        const detail = await api.get<{ run: any; phases: Phase[] }>(`/runs/${id}`);
        set({ activeDisease: detail.run?.disease_name || "" });
        if (detail.phases?.length) {
          const merged = defaultPhases();
          for (const ph of detail.phases) {
            if (merged[ph.phase]) merged[ph.phase] = { ...merged[ph.phase], status: ph.status as any };
          }
          set({ phases: merged });
        }
        const st = detail.run?.status;
        if (st === "completed") set({ runState: "completed", view: "scorecard" });
        else if (st === "failed") set({ runState: "failed" });
        else if (st === "running") set({ runState: "running", view: "matrix" });
      } catch {
        /* ignore */
      }
      get().fetchTargets(id);
    }

    // attach the live stream (replays the server-side buffer first)
    const disconnect = openStream(
      id,
      (events) => get()._applyBatch(events),
      (open) => set({ streamOpen: open })
    );
    set({ _disconnect: disconnect });
  },

  fetchTargets: async (id) => {
    const runId = id || get().activeRunId;
    if (!runId) return;
    try {
      const { targets } = await api.get<{ targets: Target[] }>(`/runs/${runId}/targets`);
      set({ targets });
    } catch {
      /* ignore */
    }
  },

  startTelemetryPoll: () => {
    const tick = async () => {
      try {
        const t = await api.get<Telemetry>("/system/telemetry");
        set({ telemetry: t });
      } catch {
        /* ignore */
      }
    };
    tick();
    const h = window.setInterval(tick, 2500);
    return () => window.clearInterval(h);
  },

  _applyBatch: (events) => {
    const s = get();
    let logs = s.logs;
    const metrics = { ...s.metrics };
    let phases = s.phases;
    let notes = s.notes;
    let telemetry = s.telemetry;
    let runState = s.runState;
    let runError = s.runError;
    let missingRequired = s.missingRequired;
    let view = s.view;
    let needTargets = false;
    let phasesDirty = false;
    const newLogs: LogLine[] = [];

    for (const e of events) {
      switch (e.type) {
        case "log":
          newLogs.push({
            seq: e.seq,
            ts: e.ts,
            level: e.level || "INFO",
            logger: e.logger || "",
            message: e.message || "",
          });
          break;
        case "metric":
          if (e.key)
            metrics[e.key] = {
              key: e.key,
              value: e.value ?? 0,
              label: e.label || e.key,
              unit: e.unit || "",
            };
          break;
        case "phase":
          if (typeof e.phase === "number") {
            if (!phasesDirty) {
              phases = phases.slice();
              phasesDirty = true;
            }
            phases[e.phase] = {
              phase: e.phase,
              name: e.name || PHASE_NAMES[e.phase],
              status: (e.status as any) || phases[e.phase].status,
            };
          }
          break;
        case "note":
          notes = [...notes, e];
          break;
        case "telemetry":
          telemetry = {
            ram_used_gb: e.ram_used_gb,
            ram_total_gb: e.ram_total_gb,
            ram_pct: e.ram_pct,
            vram_used_mb: e.vram_used_mb,
            vram_total_mb: e.vram_total_mb,
            vram_pct: e.vram_pct,
            cpu_pct: e.cpu_pct,
          };
          break;
        case "targets_ready":
          needTargets = true;
          break;
        case "run":
          if (e.status === "running") runState = "running";
          else if (e.status === "completed") {
            runState = "completed";
            needTargets = true;
            if (view === "matrix") view = "scorecard";
          } else if (e.status === "failed") {
            runState = "failed";
            runError = e.error || "Run failed";
            missingRequired = e.missing_required || [];
          }
          break;
        default:
          break;
      }
    }

    if (newLogs.length) {
      logs = logs.concat(newLogs);
      if (logs.length > LOG_CAP) logs = logs.slice(logs.length - LOG_CAP);
    }

    set({ logs, metrics, phases, notes, telemetry, runState, runError, missingRequired, view });

    if (needTargets) get().fetchTargets();
    if (runState === "completed" || runState === "failed") get().loadRuns();
  },
}));

export { PHASE_NAMES, IMPLEMENTED_MAX };

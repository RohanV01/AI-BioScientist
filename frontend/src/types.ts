// ── Shared UI types ───────────────────────────────────────────────────────────

export type PhaseStatus = 'done' | 'active' | 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface PhaseInfo {
  id: number;
  label: string;
  icon: string;
  path: string;
  status: PhaseStatus;
}

// ── Target types — used by Phase 1 / Phase 2 views ───────────────────────────

/** Normalised target row for the UI (mapped from ApiTarget in the data hooks). */
export interface Target {
  rank: number;
  symbol: string;
  mutation?: string;
  puScore: number;
  gtexExpr: 'High' | 'Med' | 'Low' | 'V.High';
  confidence: number;
  warning?: boolean;
  seeded?: boolean;
  tdl?: string;
  validationScore?: number;
  modality?: string;
  shap: { feature: string; value: number }[];
  evidenceTrail?: Record<string, unknown>;
}

export interface ValidationTarget {
  id: string;
  name: string;
  smiles: string;
  validationScore: number;
  pocketScore: number;
  plddt: number;
  status: 'Validated' | 'Processing' | 'Insignificant';
}

// ── Phase 3 ───────────────────────────────────────────────────────────────────

export interface RoutingNode {
  id: string;
  symbol: string;
  plddt: number;
  status: 'done' | 'active' | 'pending';
}

export interface ModalityBucket {
  label: string;
  count: number;
  metric: string;
  metricValue: string;
  active?: boolean;
}

// ── Phase 4 ───────────────────────────────────────────────────────────────────

export interface RepurposingDrug {
  name: string;
  target: string;
  indication: string;
  overallScore: number;
  radar: { axis: string; value: number }[];
  narrative: string;
}

// ── Phase 5 ───────────────────────────────────────────────────────────────────

export interface Molecule {
  id: string;
  smiles: string;
  qed: number;
  sa: number;
  mw: number;
  logP: number;
  lipinski: boolean;
  dockScore: number;
  method: 'REINVENT4' | 'BRICS';
}

// ── Phase 6 ───────────────────────────────────────────────────────────────────

export interface BiologicsSeq {
  id: string;
  sequence: string;
  bindingScore: number;
  hotspots: number[];
}

// ── Phase 7 ───────────────────────────────────────────────────────────────────

export interface MpoMolecule {
  id: string;
  smiles: string;
  qed: number;
  sa: number;
  dockScore: number;
  logP: number;
  mw: number;
  pareto: boolean;
}

// ── Phase 8 ───────────────────────────────────────────────────────────────────

export interface MDTimepoint {
  ns: number;
  rmsd: number;
  bindingEnergy: number;
}

// ── Run state ─────────────────────────────────────────────────────────────────

export type RunStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface RunSummaryUI {
  id: string;
  name: string;
  disease: string;
  status: RunStatus;
  currentPhase: number;
  isModule: boolean;
  modulePhase: number | null;
  costUsd: number | null;
  createdAt: string;
  intentMode: string;
  running: boolean;
}

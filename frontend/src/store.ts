import { create } from 'zustand';
import type { ApiTarget } from './lib/api';

interface AppState {
  // Home navigation (when no run is active)
  homeTab: 'dashboard' | 'new-experiment';
  setHomeTab: (t: 'dashboard' | 'new-experiment') => void;

  // Active run context — set when the user opens a run
  activeRunId: string | null;
  setActiveRunId: (id: string | null) => void;

  // Phase navigation within an active run
  activePhase: number;
  setActivePhase: (p: number) => void;

  // Inspector panel (SHAP drawer / structure viewer)
  inspectorOpen: boolean;
  setInspectorOpen: (v: boolean) => void;
  inspectorTab: 'shap' | 'viewer' | 'logs';
  setInspectorTab: (t: 'shap' | 'viewer' | 'logs') => void;

  // Selected target row (from real API data or local selection)
  selectedTarget: ApiTarget | null;
  setSelectedTarget: (t: ApiTarget | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  homeTab: 'dashboard',
  setHomeTab: (t) => set({ homeTab: t }),

  activeRunId: null,
  setActiveRunId: (id) => set({ activeRunId: id, activePhase: 0, selectedTarget: null }),

  activePhase: 1,
  setActivePhase: (p) => set({ activePhase: p }),

  inspectorOpen: false,
  setInspectorOpen: (v) => set({ inspectorOpen: v }),
  inspectorTab: 'shap',
  setInspectorTab: (t) => set({ inspectorTab: t }),

  selectedTarget: null,
  setSelectedTarget: (t) => set({ selectedTarget: t, inspectorOpen: !!t }),
}));

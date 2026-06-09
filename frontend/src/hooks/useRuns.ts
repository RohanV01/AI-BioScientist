import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import type { RunSummaryUI } from '../types';
import type { RunSummary } from '../lib/api';

function toUI(r: RunSummary): RunSummaryUI {
  return {
    id: r.id,
    name: r.disease_name,
    disease: r.disease_name,
    status: r.status,
    currentPhase: r.current_phase ?? 0,
    isModule: r.module_run ?? false,
    modulePhase: r.module_phase ?? null,
    costUsd: r.cost_usd ?? null,
    createdAt: r.created_at,
    intentMode: r.intent_mode ?? 'explore',
    running: r.running,
  };
}

/** All runs (E2E + module), refreshes every 5 s when any run is active. */
export function useRuns() {
  return useQuery({
    queryKey: ['runs'],
    queryFn: () => api.listRuns(),
    select: (data) => ({
      runs: data.runs.map(toUI),
      phaseNames: data.phase_names,
    }),
    refetchInterval: (query) => {
      const hasActive = query.state.data?.runs.some((r) => r.running);
      return hasActive ? 3000 : 10000;
    },
  });
}

/** Single run detail — polls when run is active. */
export function useRun(runId: string | null) {
  return useQuery({
    queryKey: ['run', runId],
    queryFn: () => api.getRun(runId!),
    enabled: !!runId,
    refetchInterval: (query) => (query.state.data?.running ? 3000 : false),
  });
}

/** Targets for a run — fetched once per run, invalidated on targets_ready WS event. */
export function useTargets(runId: string | null) {
  return useQuery({
    queryKey: ['targets', runId],
    queryFn: () => api.getTargets(runId!),
    enabled: !!runId,
    select: (data) => data.targets,
    staleTime: 30_000,
  });
}

/** Candidates for a run. */
export function useCandidates(runId: string | null) {
  return useQuery({
    queryKey: ['candidates', runId],
    queryFn: () => api.getCandidates(runId!),
    enabled: !!runId,
    select: (data) => data.candidates,
    staleTime: 30_000,
  });
}

/** LLM gate decisions for a run. */
export function useDecisions(runId: string | null) {
  return useQuery({
    queryKey: ['decisions', runId],
    queryFn: () => api.getDecisions(runId!),
    enabled: !!runId,
    select: (data) => data.decisions,
    staleTime: 30_000,
  });
}

/** Compute log for a run. */
export function useCompute(runId: string | null) {
  return useQuery({
    queryKey: ['compute', runId],
    queryFn: () => api.getCompute(runId!),
    enabled: !!runId,
    select: (data) => data.compute,
    staleTime: 30_000,
  });
}

/** Create an E2E run. */
export function useCreateRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createRun,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  });
}

/** Create a module run. */
export function useCreateModuleRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createModuleRun,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  });
}

/** Artifacts available for the module launcher picker. */
export function useArtifacts(artifactType?: string) {
  return useQuery({
    queryKey: ['artifacts', artifactType],
    queryFn: () => api.listArtifacts(artifactType),
    select: (data) => data.artifacts,
    staleTime: 10_000,
  });
}

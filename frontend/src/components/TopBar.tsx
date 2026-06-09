import { useAppStore } from '../store';
import { useRun } from '../hooks/useRuns';

const PHASE_LABELS: Record<number, string> = {
  0: 'Monitor',
  1: 'Target ID', 2: 'Validation', 3: 'Modality',
  4: 'Repurposing', 5: 'SM Design', 6: 'Biologics',
  7: 'MPO', 8: 'Gate', 9: 'Package',
};

export default function TopBar() {
  const { activeRunId, activePhase, setActivePhase } = useAppStore();
  const { data } = useRun(activeRunId);

  const run      = data?.run;
  const phases   = data?.phases ?? [];
  const isRunning = data?.running ?? false;

  const runLabel = run?.disease_name ?? 'BioCatalyst Lab';
  const efoId    = run?.efo_id ?? '—';

  const statusColor =
    run?.status === 'running'   ? 'var(--color-primary-container)'
    : run?.status === 'completed' ? 'var(--color-secondary)'
    : run?.status === 'failed'    ? 'var(--color-error)'
    : 'var(--color-on-surface-variant)';

  // Phase is navigable if completed or running
  function phaseAccessible(phaseNum: number): boolean {
    const pd = phases.find((p) => p.phase === phaseNum);
    return pd?.status === 'completed' || pd?.status === 'running';
  }

  return (
    <header
      className="fixed top-0 right-0 z-40 flex justify-between items-center h-14 px-5 border-b border-[var(--color-outline-variant)] glass"
      style={{ left: 'var(--spacing-sidebar)' }}
    >
      {/* Left: run context */}
      <div className="flex items-center gap-3 min-w-0">
        {/* Monitor / back button */}
        {activeRunId && activePhase !== 0 && (
          <button
            onClick={() => setActivePhase(0)}
            title="Back to Pipeline Monitor"
            className="text-[var(--color-on-surface-variant)] hover:text-[var(--color-primary-container)] transition-colors shrink-0"
          >
            <span className="material-symbols-outlined text-[18px]">arrow_back</span>
          </button>
        )}

        <span className="text-[var(--color-primary-fixed-dim)] font-semibold text-sm whitespace-nowrap truncate max-w-[180px]">
          {runLabel}
        </span>
        {run && (
          <>
            <span className="px-2 py-0.5 bg-[var(--color-surface-container-high)] border border-[var(--color-outline-variant)] rounded font-mono text-[10px] text-[var(--color-on-surface-variant)] hidden sm:block">
              {efoId}
            </span>
            <span className="flex items-center gap-1 text-[11px]" style={{ color: statusColor }}>
              {isRunning && (
                <span className="material-symbols-outlined text-[13px] animate-spin">
                  progress_activity
                </span>
              )}
              {run.status}
            </span>
          </>
        )}
      </div>

      {/* Center: phase pills — clickable, locked if not accessible */}
      {phases.length > 0 && (
        <nav className="hidden lg:flex items-center gap-0.5">
          {phases.map((p) => {
            const accessible = phaseAccessible(p.phase);
            const isViewing  = p.phase === activePhase;
            const color =
              p.status === 'completed' ? 'var(--color-secondary)'
              : p.status === 'running'  ? 'var(--color-primary-container)'
              : p.status === 'failed'   ? 'var(--color-error)'
              : 'var(--color-outline)';

            return (
              <button
                key={p.phase}
                disabled={!accessible}
                onClick={() => accessible && setActivePhase(p.phase)}
                title={`${PHASE_LABELS[p.phase] ?? `P${p.phase}`}: ${p.status}`}
                className={[
                  'px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border transition-all',
                  isViewing
                    ? 'bg-[var(--color-surface-container-high)]'
                    : accessible
                    ? 'hover:bg-[var(--color-surface-container-high)]'
                    : 'opacity-30 cursor-not-allowed',
                ].join(' ')}
                style={{
                  color,
                  borderColor: p.status === 'running' || isViewing ? color : 'transparent',
                  backgroundColor: isViewing ? 'rgba(0,0,0,0.2)' : undefined,
                }}
              >
                P{p.phase}
              </button>
            );
          })}
        </nav>
      )}

      {/* Right actions */}
      <div className="flex items-center gap-2">
        <div className="relative hidden md:block">
          <span className="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-on-surface-variant)] text-sm">
            search
          </span>
          <input
            className="bg-[var(--color-surface-container-high)] border border-[var(--color-outline-variant)] rounded pl-8 pr-3 py-1.5 text-xs text-[var(--color-on-surface)] placeholder-[var(--color-on-surface-variant)] focus:border-[var(--color-primary-container)] focus:outline-none w-36 transition-colors"
            placeholder="Search targets…"
          />
        </div>
        <button
          onClick={exportRun}
          disabled={!activeRunId}
          className="text-xs font-bold uppercase tracking-wider border border-[var(--color-outline-variant)] text-[var(--color-primary-container)] px-3 py-1.5 rounded hover:bg-[var(--color-surface-container-high)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors hidden sm:flex items-center gap-1"
        >
          <span className="material-symbols-outlined text-[14px]">download</span>
          Export
        </button>
        <div className="flex items-center gap-1.5 border-l border-[var(--color-outline-variant)] pl-2 ml-1">
          <button className="text-[var(--color-on-surface-variant)] hover:text-[var(--color-primary)] transition-colors">
            <span className="material-symbols-outlined text-xl">account_circle</span>
          </button>
        </div>
      </div>
    </header>
  );
}

// Client-side run export — downloads current run data as JSON
function exportRun() {
  const runId = useAppStore.getState().activeRunId;
  if (!runId) return;

  fetch(`/api/runs/${runId}`)
    .then((r) => r.json())
    .then((runData) => {
      return Promise.all([
        Promise.resolve(runData),
        fetch(`/api/runs/${runId}/targets`).then((r) => r.json()).catch(() => ({ targets: [] })),
        fetch(`/api/runs/${runId}/candidates`).then((r) => r.json()).catch(() => ({ candidates: [] })),
        fetch(`/api/runs/${runId}/decisions`).then((r) => r.json()).catch(() => ({ decisions: [] })),
        fetch(`/api/runs/${runId}/compute`).then((r) => r.json()).catch(() => ({ compute: [] })),
      ]);
    })
    .then(([run, targets, candidates, decisions, compute]) => {
      const blob = new Blob(
        [JSON.stringify({ run, targets, candidates, decisions, compute }, null, 2)],
        { type: 'application/json' },
      );
      const url = URL.createObjectURL(blob);
      const a   = document.createElement('a');
      a.href     = url;
      a.download = `biocatalyst-run-${runId.slice(0, 8)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    })
    .catch((err) => console.error('Export failed:', err));
}

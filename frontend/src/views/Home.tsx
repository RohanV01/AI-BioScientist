import { useMemo } from 'react';
import { useAppStore } from '../store';
import { useRuns } from '../hooks/useRuns';
import type { RunSummaryUI } from '../types';

const PIPELINE_PHASES = [
  { id: 1, label: 'Target ID',     icon: 'biotech'     },
  { id: 2, label: 'Validation',    icon: 'verified'    },
  { id: 3, label: 'Routing',       icon: 'hub'         },
  { id: 4, label: 'Repurposing',   icon: 'rebase_edit' },
  { id: 5, label: 'De Novo SM',    icon: 'medication'  },
  { id: 6, label: 'Biologics',     icon: 'polymer'     },
  { id: 7, label: 'MPO',           icon: 'analytics'   },
  { id: 8, label: 'Packaging',     icon: 'inventory_2' },
];

const MODE_CARDS = [
  {
    mode:  'explore'  as const,
    icon:  'biotech',
    label: 'Target Exploration',
    desc:  'PU learning + multi-omics to identify novel druggable targets.',
  },
  {
    mode:  'repurpose' as const,
    icon:  'rebase_edit',
    label: 'Drug Repurposing',
    desc:  'Screen approved compounds via ChEMBL docking.',
  },
  {
    mode:  'de_novo'  as const,
    icon:  'medication',
    label: 'De Novo Design',
    desc:  'Generate novel SMs via REINVENT4 + LLM-guided biologics.',
  },
];

const STATUS_DOT: Record<string, string> = {
  completed: 'bg-[var(--color-secondary)]',
  running:   'bg-[var(--color-primary-container)] animate-pulse',
  failed:    'bg-[var(--color-error)]',
  pending:   'bg-[var(--color-outline)]',
};

function RunRow({ run, onClick }: { run: RunSummaryUI; onClick: () => void }) {
  const dotCls = STATUS_DOT[run.status] ?? STATUS_DOT.pending;
  const date = new Date(run.createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-4 py-3 rounded hover:bg-[var(--color-surface-container-high)] transition-colors text-left group"
    >
      <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotCls}`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-[var(--color-on-surface)] group-hover:text-[var(--color-primary-container)] transition-colors truncate">
          {run.disease}
        </p>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className="text-[10px] font-mono text-[var(--color-on-surface-variant)]">{date}</span>
          <span className="text-[var(--color-outline)] text-[10px]">·</span>
          <span className="text-[10px] capitalize text-[var(--color-on-surface-variant)]">{run.intentMode}</span>
        </div>
        <div className="flex gap-0.5 mt-1.5">
          {Array.from({ length: 9 }, (_, i) => (
            <div
              key={i}
              className={`h-px flex-1 rounded-sm ${
                i < run.currentPhase
                  ? run.status === 'completed' ? 'bg-[var(--color-secondary)]' : 'bg-[var(--color-primary-container)]'
                  : 'bg-[var(--color-outline-variant)]'
              }`}
            />
          ))}
        </div>
      </div>
      <span className="text-[10px] font-mono text-[var(--color-on-surface-variant)] shrink-0">P{run.currentPhase}</span>
    </button>
  );
}

export default function Home() {
  const { setActiveRunId, setHomeTab } = useAppStore();
  const { data: runsData, isLoading } = useRuns();

  const e2eRuns = useMemo(
    () => (runsData?.runs ?? []).filter((r) => !r.isModule),
    [runsData],
  );

  const stats = useMemo(() => {
    const total = e2eRuns.length;
    const completed = e2eRuns.filter((r) => r.status === 'completed').length;
    const running = e2eRuns.filter((r) => r.status === 'running').length;
    const failed = e2eRuns.filter((r) => r.status === 'failed').length;
    const successRate = completed + failed > 0 ? Math.round((completed / (completed + failed)) * 100) : null;
    return { total, completed, running, successRate };
  }, [e2eRuns]);

  const recentRuns = useMemo(
    () => [...e2eRuns].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()).slice(0, 10),
    [e2eRuns],
  );

  const hasRuns = e2eRuns.length > 0;

  return (
    <div className="h-full flex flex-col bg-[var(--color-background)] text-[var(--color-on-surface)]">

      {/* ── Top bar ────────────────────────────────────────────────────── */}
      <div className="shrink-0 flex items-center justify-between px-8 h-14 border-b border-[var(--color-outline-variant)]">
        <div className="flex items-center gap-3">
          <img src="/logo-bw.svg" alt="BioCatalyst Lab" className="w-5 h-5 shrink-0" />
          <h1 className="text-sm font-semibold text-[var(--color-on-surface)]">BioCatalyst Lab</h1>
          <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">Drug Discovery Pipeline</span>
        </div>
        <button
          onClick={() => setHomeTab('new-experiment')}
          className="flex items-center gap-1.5 px-4 py-2 rounded text-sm font-semibold bg-[var(--color-primary-container)] text-[var(--color-on-primary)] hover:bg-[var(--color-primary)] transition-colors"
        >
          <span className="material-symbols-outlined text-[15px]">add</span>
          New Experiment
        </button>
      </div>

      {/* ── Two-column body ───────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">

        {/* LEFT: pipeline reference + mode quick-select (35%) */}
        <div className="w-[35%] border-r border-[var(--color-outline-variant)] flex flex-col overflow-y-auto">

          {/* Pipeline node chain */}
          <div className="px-6 pt-5 pb-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-4">
              Pipeline
            </p>
            {PIPELINE_PHASES.map((p, idx) => (
              <div key={p.id} className="flex items-start gap-3">
                <div className="flex flex-col items-center shrink-0" style={{ width: 24 }}>
                  <div className="w-6 h-6 rounded-full border border-[var(--color-outline-variant)] bg-[var(--color-surface-container)] flex items-center justify-center shrink-0">
                    <span className="text-[9px] font-bold font-mono text-[var(--color-on-surface-variant)]">{p.id}</span>
                  </div>
                  {idx < PIPELINE_PHASES.length - 1 && (
                    <div className="w-px bg-[var(--color-outline-variant)]" style={{ height: 20 }} />
                  )}
                </div>
                <div className="flex items-center gap-2 h-6 mb-[20px]" style={idx === PIPELINE_PHASES.length - 1 ? { marginBottom: 0 } : {}}>
                  <span
                    className="material-symbols-outlined text-[13px] text-[var(--color-on-surface-variant)] shrink-0"
                    style={{ fontVariationSettings: "'FILL' 1" }}
                  >
                    {p.icon}
                  </span>
                  <span className="text-[12px] text-[var(--color-on-surface-variant)]">{p.label}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="mx-6 border-t border-[var(--color-outline-variant)]" />

          {/* Start with: mode quick-select */}
          <div className="px-6 py-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-3">
              Start with
            </p>
            <div className="space-y-1.5">
              {MODE_CARDS.map((card) => (
                <button
                  key={card.mode}
                  onClick={() => setHomeTab('new-experiment')}
                  className="w-full text-left flex items-start gap-3 px-3 py-2.5 rounded border border-[var(--color-outline-variant)] bg-[var(--color-surface-container)] hover:bg-[var(--color-surface-container-high)] hover:border-[var(--color-outline)] transition-all group"
                >
                  <span
                    className="material-symbols-outlined text-[14px] text-[var(--color-on-surface-variant)] group-hover:text-[var(--color-on-surface)] mt-0.5 shrink-0 transition-colors"
                    style={{ fontVariationSettings: "'FILL' 1" }}
                  >
                    {card.icon}
                  </span>
                  <div>
                    <p className="text-[12px] font-medium text-[var(--color-on-surface-variant)] group-hover:text-[var(--color-on-surface)] transition-colors">
                      {card.label}
                    </p>
                    <p className="text-[10px] text-[var(--color-on-surface-variant)]/60 mt-0.5 leading-snug">{card.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* RIGHT: experiments (65%) */}
        <div className="flex-1 flex flex-col min-h-0">

          {/* Stats strip — only when runs exist */}
          {!isLoading && hasRuns && (
            <div className="shrink-0 flex border-b border-[var(--color-outline-variant)] divide-x divide-[var(--color-outline-variant)]">
              {[
                { value: stats.total,        label: 'Experiments' },
                { value: stats.completed,    label: 'Completed'   },
                { value: stats.running,      label: 'Running'     },
                { value: stats.successRate != null ? `${stats.successRate}%` : '—', label: 'Success rate' },
              ].map(({ value, label }) => (
                <div key={label} className="flex-1 flex flex-col items-center gap-0.5 px-4 py-4">
                  <span className="text-xl font-bold font-mono text-[var(--color-on-surface)]">{value}</span>
                  <span className="text-[10px] uppercase tracking-wider text-[var(--color-on-surface-variant)]">{label}</span>
                </div>
              ))}
            </div>
          )}

          {/* Section header */}
          <div className="shrink-0 flex items-center justify-between px-6 pt-5 pb-3">
            <div className="flex items-center gap-2">
              <h2 className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">
                Recent Experiments
              </h2>
              {hasRuns && (
                <span className="text-[11px] font-mono text-[var(--color-on-surface-variant)]">{e2eRuns.length}</span>
              )}
            </div>
          </div>

          {/* List / empty state */}
          <div className="flex-1 overflow-y-auto px-2 pb-4">
            {isLoading && (
              <div className="flex items-center justify-center py-12">
                <span className="material-symbols-outlined text-xl text-[var(--color-on-surface-variant)] animate-spin">
                  progress_activity
                </span>
              </div>
            )}

            {!isLoading && recentRuns.map((run) => (
              <RunRow key={run.id} run={run} onClick={() => setActiveRunId(run.id)} />
            ))}

            {!isLoading && !hasRuns && (
              <div className="mx-4 mt-1 rounded border border-dashed border-[var(--color-outline-variant)] px-4 py-5 flex items-center gap-3 text-[var(--color-on-surface-variant)]">
                <span className="material-symbols-outlined text-[18px]">science</span>
                <span className="text-sm">No experiments yet — configure one above.</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

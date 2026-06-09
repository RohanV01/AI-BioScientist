import { useState } from 'react';
import { useAppStore } from '../store';
import { useRuns, useRun } from '../hooks/useRuns';


const PHASES = [
  { id: 1, label: 'Target ID',         icon: 'biotech'      },
  { id: 2, label: 'Validation',        icon: 'verified'     },
  { id: 3, label: 'Routing',           icon: 'hub'          },
  { id: 4, label: 'Repurposing',       icon: 'rebase_edit'  },
  { id: 5, label: 'De Novo SM',        icon: 'medication'   },
  { id: 6, label: 'Biologics',         icon: 'polymer'      },
  { id: 7, label: 'MPO',               icon: 'analytics'    },
  { id: 8, label: 'Packaging',         icon: 'inventory_2'  },
];

const STATUS_ICON: Record<string, string> = {
  running:   'pending',
  completed: 'check_circle',
  failed:    'cancel',
  pending:   'radio_button_unchecked',
};

const STATUS_COLOR: Record<string, string> = {
  running:   'var(--color-primary-container)',
  completed: 'var(--color-secondary)',
  failed:    'var(--color-error)',
  pending:   'var(--color-on-surface-variant)',
};

export default function Sidebar() {
  const { activePhase, setActivePhase, activeRunId, setActiveRunId, homeTab, setHomeTab } = useAppStore();
  const { data: runsData, isLoading } = useRuns();
  const { data: runDetail } = useRun(activeRunId);

  const [runsExpanded, setRunsExpanded] = useState(true);

  const runs       = runsData?.runs ?? [];
  const e2eRuns    = runs.filter((r) => !r.isModule);
  const moduleRuns = runs.filter((r) => r.isModule);
  const activeRun  = runs.find((r) => r.id === activeRunId);
  const recentRuns = [...runs]
    .sort((a, b) => new Date(b.createdAt ?? '').getTime() - new Date(a.createdAt ?? '').getTime())
    .slice(0, 5);

  // Phase status from the live run detail (for nav guards)
  const phaseStatuses = Object.fromEntries(
    (runDetail?.phases ?? []).map((p) => [p.phase, p.status])
  );

  function phaseAccessible(id: number): boolean {
    const s = phaseStatuses[id];
    return s === 'completed' || s === 'running';
  }

  return (
    <nav
      className="fixed left-0 top-0 h-full flex flex-col border-r border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)] z-30"
      style={{ width: 'var(--spacing-sidebar)' }}
    >
      {/* Header */}
      <div
        className="px-5 pt-5 pb-4 border-b border-[var(--color-outline-variant)] shrink-0 cursor-pointer group"
        onClick={() => { setActiveRunId(null); setHomeTab('dashboard'); }}
        title="Back to home"
      >
        <div className="flex items-center gap-2 mb-0.5">
          <img
            src="/logo-bw.svg"
            alt="BioCatalyst Lab"
            className="w-5 h-5 shrink-0 group-hover:scale-110 transition-transform"
          />
          <h1 className="text-[var(--color-primary-container)] font-bold text-sm truncate tracking-tight group-hover:text-[var(--color-primary)] transition-colors">
            BioCatalyst Lab
          </h1>
        </div>
        <p className="text-[var(--color-on-surface-variant)] text-[10px] font-bold uppercase tracking-widest ml-7">
          {activeRun ? activeRun.disease : 'Drug Discovery AI'}
        </p>
      </div>

      {/* Home nav — only visible when no run is active */}
      {!activeRunId && (
        <div className="border-b border-[var(--color-outline-variant)] py-2 px-3 space-y-0.5">
          {[
            { tab: 'dashboard' as const,       icon: 'dashboard',   label: 'Overview'        },
            { tab: 'new-experiment' as const,  icon: 'add_circle',  label: 'New Experiment'  },
          ].map(({ tab, icon, label }) => (
            <button
              key={tab}
              onClick={() => setHomeTab(tab)}
              className={[
                'w-full flex items-center gap-3 px-3 py-2 rounded text-left transition-all text-[13px]',
                homeTab === tab
                  ? 'text-[var(--color-primary-container)] font-semibold bg-[var(--color-surface-container-high)] border-l-2 border-[var(--color-primary-container)] pl-[10px]'
                  : 'text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-on-surface)]',
              ].join(' ')}
            >
              <span
                className="material-symbols-outlined text-[18px] shrink-0"
                style={homeTab === tab ? { fontVariationSettings: "'FILL' 1", color: 'var(--color-primary-container)' } : undefined}
              >
                {icon}
              </span>
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Phase nav — only visible when a run is active */}
      {activeRunId && (
        <div className="border-b border-[var(--color-outline-variant)] py-2">
          {/* Mission Control link */}
          <div className="px-3 mb-1">
            <button
              onClick={() => setActivePhase(0)}
              className={[
                'w-full flex items-center gap-3 px-3 py-2 rounded text-left transition-all text-[13px]',
                activePhase === 0
                  ? 'text-[var(--color-primary-container)] font-semibold bg-[var(--color-surface-container-high)] border-l-2 border-[var(--color-primary-container)] pl-[10px]'
                  : 'text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-on-surface)]',
              ].join(' ')}
            >
              <span
                className={`material-symbols-outlined text-[18px] shrink-0 ${
                  activePhase === 0 ? 'text-[var(--color-primary-container)]' : 'text-[var(--color-on-surface-variant)]'
                }`}
                style={activePhase === 0 ? { fontVariationSettings: "'FILL' 1" } : undefined}
              >
                dashboard
              </span>
              <span>Pipeline Monitor</span>
              {runDetail?.running && activePhase !== 0 && (
                <span className="ml-auto w-1.5 h-1.5 rounded-full bg-[var(--color-primary-container)] animate-ping shrink-0" />
              )}
            </button>
          </div>

          {/* Phase list */}
          <ul className="space-y-0.5 px-3">
            {PHASES.map(({ id, label, icon }) => {
              const isActive   = id === activePhase;
              const accessible = phaseAccessible(id);
              const status     = phaseStatuses[id] ?? 'pending';
              const isDone     = status === 'completed';
              const isRunning  = status === 'running';

              return (
                <li key={id}>
                  <button
                    onClick={() => accessible && setActivePhase(id)}
                    disabled={!accessible}
                    title={!accessible ? `Phase ${id} hasn't started yet` : undefined}
                    className={[
                      'w-full flex items-center gap-3 px-3 py-2 rounded text-left transition-all text-[13px]',
                      isActive && accessible
                        ? 'text-[var(--color-primary-container)] font-semibold border-l-2 border-[var(--color-primary-container)] bg-[var(--color-surface-container-high)] pl-[10px]'
                        : accessible
                        ? 'text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-on-surface)]'
                        : 'text-[var(--color-on-surface-variant)]/30 cursor-not-allowed',
                    ].join(' ')}
                  >
                    <span
                      className={`material-symbols-outlined text-[18px] shrink-0 ${
                        isDone   ? 'text-[var(--color-secondary)]'
                        : isRunning ? 'text-[var(--color-primary-container)]'
                        : isActive  ? 'text-[var(--color-primary-container)]'
                        : accessible ? 'text-[var(--color-on-surface-variant)]'
                        : 'text-[var(--color-on-surface-variant)]/30'
                      }`}
                      style={(isDone || isActive) ? { fontVariationSettings: "'FILL' 1" } : undefined}
                    >
                      {isDone ? 'check_circle' : isRunning ? 'pending' : icon}
                    </span>
                    <span className="truncate">{label}</span>
                    {isActive && accessible && (
                      <span className="ml-auto w-1.5 h-1.5 rounded-full bg-[var(--color-primary-container)] animate-blink shrink-0" />
                    )}
                    {isRunning && !isActive && (
                      <span className="ml-auto w-1.5 h-1.5 rounded-full bg-[var(--color-primary-container)] animate-ping shrink-0" />
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Collapsible recent runs */}
      <div className="flex-1 overflow-y-auto min-h-0 py-2">
        {isLoading && (
          <p className="px-5 text-[11px] text-[var(--color-on-surface-variant)] py-2">Loading…</p>
        )}

        {!isLoading && runs.length > 0 && (
          <div>
            {/* Section header */}
            <button
              onClick={() => setRunsExpanded((v) => !v)}
              className="w-full flex items-center justify-between px-5 py-1.5 text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] hover:text-[var(--color-on-surface)] transition-colors"
            >
              <span>Recent Runs</span>
              <span className="material-symbols-outlined text-[13px]">
                {runsExpanded ? 'expand_less' : 'expand_more'}
              </span>
            </button>

            {runsExpanded && (
              <ul className="space-y-0.5 px-3 mt-0.5">
                {recentRuns.map((r) => (
                  <RunRow
                    key={r.id}
                    run={r}
                    active={r.id === activeRunId}
                    onClick={() => setActiveRunId(r.id)}
                    label={r.isModule && r.modulePhase != null ? `P${r.modulePhase} · ` : ''}
                  />
                ))}
                {runs.length > 5 && (
                  <li className="px-3 py-1">
                    <span className="text-[10px] text-[var(--color-on-surface-variant)]/50">
                      +{runs.length - 5} more
                    </span>
                  </li>
                )}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-3 pb-4 pt-2 border-t border-[var(--color-outline-variant)] shrink-0 space-y-0.5">
        {[{ icon: 'settings', label: 'Settings' }, { icon: 'help', label: 'Support' }].map(({ icon, label }) => (
          <button
            key={label}
            className="w-full flex items-center gap-3 px-3 py-2 rounded text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-container-highest)] hover:text-[var(--color-on-surface)] transition-colors text-[13px]"
          >
            <span className="material-symbols-outlined text-[18px]">{icon}</span>
            {label}
          </button>
        ))}
        <button
          onClick={() => { setActiveRunId(null); setHomeTab('new-experiment'); }}
          className="mt-2 w-full bg-[var(--color-primary-container)] text-[var(--color-on-primary-container)] py-2.5 px-3 rounded text-xs font-bold uppercase tracking-wider hover:bg-[var(--color-surface-tint)] transition-colors flex items-center justify-center gap-1.5"
        >
          <span className="material-symbols-outlined text-base">add</span>
          New Experiment
        </button>
      </div>
    </nav>
  );
}

// ── Run row sub-component ─────────────────────────────────────────────────────

interface RunRowProps {
  run: { id: string; name: string; status: string; currentPhase: number };
  active: boolean;
  onClick: () => void;
  label?: string;
}

function RunRow({ run, active, onClick, label = '' }: RunRowProps) {
  const icon     = STATUS_ICON[run.status]  ?? 'radio_button_unchecked';
  const color    = STATUS_COLOR[run.status] ?? 'var(--color-on-surface-variant)';
  const isRunning = run.status === 'running';

  return (
    <li>
      <button
        onClick={onClick}
        className={[
          'w-full flex items-center gap-2 px-3 py-2 rounded text-left transition-all text-[12px]',
          active
            ? 'bg-[var(--color-surface-container-high)] text-[var(--color-on-surface)]'
            : 'text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-on-surface)]',
        ].join(' ')}
      >
        <span
          className={`material-symbols-outlined text-[16px] shrink-0 ${isRunning ? 'animate-spin' : ''}`}
          style={{ color, fontVariationSettings: "'FILL' 1" }}
        >
          {icon}
        </span>
        <span className="truncate">{label}{run.name}</span>
        {isRunning && (
          <span className="ml-auto text-[10px] text-[var(--color-on-surface-variant)] shrink-0 font-mono">
            P{run.currentPhase}
          </span>
        )}
      </button>
    </li>
  );
}

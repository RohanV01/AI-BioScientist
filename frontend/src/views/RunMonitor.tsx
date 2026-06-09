import { useEffect, useRef } from 'react';
import { useAppStore } from '../store';
import { useRun } from '../hooks/useRuns';
import { useRunEvents } from '../hooks/useRunEvents';
import type { StreamEvent } from '../lib/api';

const PHASE_META: Record<number, { label: string; icon: string }> = {
  0: { label: 'Setup',      icon: 'settings'     },
  1: { label: 'Target ID',  icon: 'biotech'      },
  2: { label: 'Validation', icon: 'verified'     },
  3: { label: 'Routing',    icon: 'hub'          },
  4: { label: 'Repurpose',  icon: 'rebase_edit'  },
  5: { label: 'De Novo SM', icon: 'medication'   },
  6: { label: 'Biologics',  icon: 'polymer'      },
  7: { label: 'MPO',        icon: 'analytics'    },
  8: { label: 'Package',    icon: 'inventory_2'  },
};

function fmtTs(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('en-US', {
    hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function fmtDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return '';
  const ms = (finishedAt ? new Date(finishedAt).getTime() : Date.now()) - new Date(startedAt).getTime();
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function evtLabel(evt: StreamEvent): string {
  if (evt.type === 'phase') return `Phase ${evt.phase} — ${evt.status}${evt.error ? `: ${evt.error}` : ''}`;
  if (evt.type === 'run') return `Run ${evt.status}`;
  if (evt.type === 'targets_ready') return `Targets ready — ${evt.count ?? '?'} scored`;
  if (evt.type === 'metric') return `${String(evt.key ?? 'metric')}: ${String(evt.value ?? '')}`;
  if (evt.type === 'step') return String(evt.message ?? evt.step ?? evt.msg ?? '');
  if (evt.type === 'note' || evt.type === 'log') return String(evt.message ?? evt.msg ?? evt.text ?? '');
  if (evt.type === 'synced') return 'Event replay synced';
  return JSON.stringify(evt).slice(0, 120);
}

function evtRowClass(evt: StreamEvent): string {
  const s = evt.status as string | undefined;
  if (evt.type === 'run'    && s === 'completed') return 'text-[var(--color-secondary)]';
  if (evt.type === 'run'    && s === 'failed')    return 'text-[var(--color-error)]';
  if (evt.type === 'phase'  && s === 'completed') return 'text-[var(--color-secondary)]';
  if (evt.type === 'phase'  && s === 'running')   return 'text-[var(--color-primary-container)]';
  if (evt.type === 'phase'  && s === 'failed')    return 'text-[var(--color-error)]';
  if (evt.type === 'targets_ready')               return 'text-[var(--color-secondary)]';
  if (evt.type === 'metric')                      return 'text-[#d0bcff]';
  return 'text-[var(--color-on-surface-variant)]';
}

const TAG_CLS: Record<string, string> = {
  phase:         'text-[var(--color-primary-container)] bg-[var(--color-primary-container)]/10',
  run:           'text-[var(--color-secondary)] bg-[var(--color-secondary)]/10',
  metric:        'text-[#d0bcff] bg-[#d0bcff]/10',
  targets_ready: 'text-[var(--color-secondary)] bg-[var(--color-secondary)]/15',
  step:          'text-[var(--color-on-surface-variant)] bg-[var(--color-surface-container-high)]',
  note:          'text-[var(--color-outline)] bg-[var(--color-surface-container)]',
  log:           'text-[var(--color-outline)] bg-[var(--color-surface-container)]',
  synced:        'text-[var(--color-outline)] bg-[var(--color-surface-container)]',
};

export default function RunMonitor() {
  const { activeRunId, setActivePhase } = useAppStore();
  const { data: runData } = useRun(activeRunId);
  const events = useRunEvents(activeRunId);
  const logRef = useRef<HTMLDivElement>(null);
  const autoScroll = useRef(true);

  // Auto-scroll only when user hasn't scrolled up
  useEffect(() => {
    const el = logRef.current;
    if (!el || !autoScroll.current) return;
    el.scrollTop = el.scrollHeight;
  }, [events.length]);

  const run       = runData?.run;
  const phases    = runData?.phases ?? [];
  const isRunning = runData?.running ?? false;

  const completedCount = phases.filter((p) => p.status === 'completed').length;
  const totalPhases    = Math.max(phases.length, 1);
  const progress       = (completedCount / totalPhases) * 100;
  const activePh       = phases.find((p) => p.status === 'running');

  const statusColor = run?.status === 'completed' ? 'var(--color-secondary)'
    : run?.status === 'failed'    ? 'var(--color-error)'
    : run?.status === 'running'   ? 'var(--color-primary-container)'
    : 'var(--color-on-surface-variant)';

  return (
    <div className="max-w-5xl mx-auto space-y-5">

      {/* ── Status hero ── */}
      <div className="bg-[var(--color-surface-container-low)] border border-[var(--color-outline-variant)] rounded-xl p-5 relative overflow-hidden">
        {isRunning && (
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.04)_0%,transparent_60%)] pointer-events-none" />
        )}
        <div className="flex items-start justify-between relative">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              {isRunning ? (
                <span className="material-symbols-outlined text-base animate-spin" style={{ color: statusColor }}>
                  progress_activity
                </span>
              ) : (
                <span
                  className="material-symbols-outlined text-base"
                  style={{ color: statusColor, fontVariationSettings: "'FILL' 1" }}
                >
                  {run?.status === 'completed' ? 'check_circle' : run?.status === 'failed' ? 'error' : 'pending'}
                </span>
              )}
              <h2 className="text-lg font-bold text-[var(--color-on-surface)] truncate">
                {run?.disease_name ?? 'Initializing…'}
              </h2>
              {run?.efo_id && (
                <span className="font-mono text-[11px] px-2 py-0.5 bg-[var(--color-surface-container-high)] border border-[var(--color-outline-variant)] rounded text-[var(--color-on-surface-variant)] shrink-0">
                  {run.efo_id}
                </span>
              )}
            </div>
            <p className="text-sm text-[var(--color-on-surface-variant)] ml-6">
              {activePh
                ? `Running Phase ${activePh.phase} · ${PHASE_META[activePh.phase]?.label ?? ''}`
                : run?.status === 'completed'
                ? `All ${completedCount} phases complete`
                : run?.status === 'failed'
                ? 'Pipeline failed — check event log below'
                : 'Pipeline queued…'}
            </p>
          </div>

          {run?.status === 'completed' && (
            <button
              onClick={() => setActivePhase(1)}
              className="ml-4 shrink-0 bg-[var(--color-primary-container)] text-[var(--color-on-primary-container)] px-4 py-2 rounded text-xs font-bold uppercase tracking-wider hover:bg-[var(--color-surface-tint)] transition-colors flex items-center gap-1.5 shadow-[0_0_16px_rgba(255,255,255,0.2)]"
            >
              <span className="material-symbols-outlined text-base">biotech</span>
              Explore Results
            </button>
          )}
        </div>

        {/* Progress bar */}
        <div className="mt-4 w-full h-1 bg-[var(--color-surface-container-highest)] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${progress}%`,
              background: run?.status === 'failed'
                ? 'var(--color-error)'
                : 'linear-gradient(90deg, var(--color-primary-container), var(--color-secondary))',
            }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-[var(--color-outline)] font-mono mt-1">
          <span>Phase 0</span>
          <span>{completedCount}/{totalPhases} complete</span>
          <span>Phase 8</span>
        </div>
      </div>

      {/* ── Phase timeline cards ── */}
      <div className="grid grid-cols-5 gap-2">
        {Array.from({ length: 9 }, (_, phaseNum) => {
          const meta      = PHASE_META[phaseNum] ?? { label: `P${phaseNum}`, icon: 'circle' };
          const phaseData = phases.find((p) => p.phase === phaseNum);
          const status    = phaseData?.status ?? 'pending';
          const isDone    = status === 'completed';
          const isActive  = status === 'running';
          const isFailed  = status === 'failed';
          const isLocked  = !isDone && !isActive && !isFailed;
          const duration  = isDone ? fmtDuration(phaseData?.started_at ?? null, phaseData?.finished_at ?? null) : null;
          const targetPhase = phaseNum === 0 ? 1 : phaseNum;

          return (
            <button
              key={phaseNum}
              disabled={isLocked}
              onClick={() => !isLocked && setActivePhase(targetPhase)}
              title={isLocked ? `Phase ${phaseNum} not started` : `Go to Phase ${phaseNum} results`}
              className={[
                'relative rounded-xl border p-3 text-left transition-all text-xs',
                isDone
                  ? 'border-[var(--color-secondary)]/40 bg-[var(--color-secondary)]/5 hover:bg-[var(--color-secondary)]/10 cursor-pointer group'
                  : isActive
                  ? 'border-[var(--color-primary-container)]/60 bg-[var(--color-primary-container)]/5 cursor-pointer'
                  : isFailed
                  ? 'border-[var(--color-error)]/40 bg-[var(--color-error)]/5 cursor-pointer'
                  : 'border-[var(--color-outline-variant)]/50 bg-[var(--color-surface-container-lowest)] opacity-40 cursor-not-allowed',
              ].join(' ')}
            >
              {/* Status icon */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-[9px] font-bold uppercase tracking-widest text-[var(--color-outline)]">
                  P{phaseNum}
                </span>
                {isDone ? (
                  <span
                    className="material-symbols-outlined text-sm text-[var(--color-secondary)]"
                    style={{ fontVariationSettings: "'FILL' 1" }}
                  >
                    check_circle
                  </span>
                ) : isActive ? (
                  <span className="material-symbols-outlined text-sm text-[var(--color-primary-container)] animate-spin">
                    progress_activity
                  </span>
                ) : isFailed ? (
                  <span
                    className="material-symbols-outlined text-sm text-[var(--color-error)]"
                    style={{ fontVariationSettings: "'FILL' 1" }}
                  >
                    error
                  </span>
                ) : (
                  <span className="material-symbols-outlined text-sm text-[var(--color-outline)]">
                    {meta.icon}
                  </span>
                )}
              </div>

              <p className="font-semibold text-[var(--color-on-surface)] leading-tight text-[11px]">{meta.label}</p>

              {/* Sub-info */}
              {duration ? (
                <p className="text-[9px] font-mono text-[var(--color-secondary)] mt-1">{duration}</p>
              ) : isActive ? (
                <p className="text-[9px] text-[var(--color-primary-container)] mt-1 animate-pulse">Running…</p>
              ) : null}

              {/* Hover CTA on done cards */}
              {isDone && phaseNum > 0 && (
                <p className="text-[9px] text-[var(--color-outline)] mt-1 group-hover:text-[var(--color-primary-container)] transition-colors flex items-center gap-0.5">
                  <span className="material-symbols-outlined text-[10px]">arrow_forward</span>
                  View
                </p>
              )}
            </button>
          );
        })}
      </div>

      {/* ── Live event log ── */}
      <div className="bg-[var(--color-surface-container-lowest)] border border-[var(--color-outline-variant)] rounded-xl overflow-hidden">
        {/* Log header */}
        <div className="px-4 py-2.5 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            {isRunning && (
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--color-primary-container)] opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--color-primary-container)]" />
              </span>
            )}
            <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">
              Event Stream
            </p>
            <span className="font-mono text-[10px] text-[var(--color-outline)]">{events.length} events</span>
          </div>
          <span className={`text-[10px] font-mono ${isRunning ? 'text-[var(--color-primary-container)]' : 'text-[var(--color-outline)]'}`}>
            {isRunning ? '● live' : '○ ended'}
          </span>
        </div>

        {/* Log body */}
        <div
          ref={logRef}
          className="h-72 overflow-y-auto p-3 font-mono text-[11px] space-y-0.5"
          onScroll={(e) => {
            const el = e.currentTarget;
            autoScroll.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
          }}
        >
          {events.length === 0 ? (
            <p className="text-[var(--color-outline)] italic py-2 px-1">Waiting for pipeline events…</p>
          ) : (
            events.map((evt, i) => (
              <div key={evt.seq ?? i} className={`flex items-start gap-3 py-0.5 ${evtRowClass(evt)}`}>
                <span className="text-[var(--color-surface-container-highest)] shrink-0 w-20 text-right select-none">
                  {fmtTs(evt.ts)}
                </span>
                <span
                  className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded shrink-0 min-w-[52px] text-center ${TAG_CLS[evt.type] ?? 'text-[var(--color-outline)] bg-[var(--color-surface-container)]'}`}
                >
                  {evt.type}
                </span>
                <span className="leading-relaxed break-words flex-1 min-w-0">{evtLabel(evt)}</span>
              </div>
            ))
          )}
        </div>
      </div>

    </div>
  );
}

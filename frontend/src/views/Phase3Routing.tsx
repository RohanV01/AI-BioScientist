import { useState } from 'react';
import { useAppStore } from '../store';
import { useTargets, useDecisions } from '../hooks/useRuns';

const MODALITY_META: Record<string, { icon: string; color: string }> = {
  'Small Molecule': { icon: 'medication',  color: 'var(--color-primary-container)' },
  'Biologic':       { icon: 'polymer',     color: 'var(--color-secondary)' },
  'PROTAC':         { icon: 'auto_awesome',color: '#d0bcff' },
  'Repurposing':    { icon: 'rebase_edit', color: '#fbbf24' },
  'Unknown':        { icon: 'help_outline',color: 'var(--color-outline)' },
};

function modalityKey(raw: string | null | undefined): string {
  if (!raw) return 'Unknown';
  const r = raw.toLowerCase();
  if (r.includes('protac') || r.includes('degrader')) return 'PROTAC';
  if (r.includes('repurpos')) return 'Repurposing';
  if (r.includes('biolog') || r.includes('antibody') || r.includes('peptide')) return 'Biologic';
  if (r.includes('small') || r.includes('sm')) return 'Small Molecule';
  return raw;
}

export default function Phase3Routing() {
  const { activeRunId } = useAppStore();
  const { data: targets = [], isLoading } = useTargets(activeRunId);
  const { data: decisions = [] } = useDecisions(activeRunId);

  const top5 = [...targets]
    .sort((a, b) => (b.validation_score ?? b.aggregate_score) - (a.validation_score ?? a.aggregate_score))
    .slice(0, 5);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const effective = selectedId ?? top5[1]?.symbol ?? top5[0]?.symbol ?? null;

  // Compute modality bucket counts
  const bucketMap: Record<string, number> = {};
  for (const t of targets) {
    const key = modalityKey(t.modality_primary);
    bucketMap[key] = (bucketMap[key] ?? 0) + 1;
  }
  const buckets = Object.entries(bucketMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);

  // P3 gate decision narrative
  const p3Decision = decisions.find((d) => d.phase === 3);

  const routed = targets.filter((t) => t.modality_primary).length;
  const routedPct = targets.length ? Math.round((routed / targets.length) * 100) : 0;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="material-symbols-outlined text-4xl text-[var(--color-outline)] animate-spin">progress_activity</span>
      </div>
    );
  }

  if (targets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-[var(--color-on-surface-variant)]">
        <span className="material-symbols-outlined text-5xl">hub</span>
        <p className="text-base font-semibold">Phase 3 hasn't completed yet</p>
        <p className="text-sm">Modality routing runs after target validation (Phase 2).</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-2xl font-bold text-[var(--color-on-surface)] mb-1">Modality Routing Network</h2>
          <p className="text-sm text-[var(--color-on-surface-variant)]">
            {targets.length} validated targets routed into optimal therapeutic modality buckets.
          </p>
        </div>
        <div className="flex gap-3">
          <MiniStat label="Input Targets" value={String(targets.length)} />
          <MiniStat label="Routed" value={`${routedPct}%`} green />
        </div>
      </div>

      {/* Sankey canvas */}
      <div
        className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-6 relative overflow-hidden"
        style={{ minHeight: 440 }}
      >
        {/* Controls */}
        <div className="absolute top-4 left-4 z-10 flex gap-2">
          <div className="bg-[var(--color-surface)] border border-[var(--color-outline-variant)] rounded px-2 py-1 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[var(--color-secondary)]" />
            <span className="text-[10px] text-[var(--color-on-surface-variant)]">High Confidence</span>
            <span className="w-2 h-2 rounded-full bg-[var(--color-primary-container)] ml-2" />
            <span className="text-[10px] text-[var(--color-on-surface-variant)]">Tractable</span>
          </div>
        </div>

        <div className="flex items-center justify-between mt-10 h-80 px-4">
          {/* Left: real target nodes */}
          <div className="w-44 space-y-3 flex flex-col justify-around h-full">
            {top5.map((t, i) => {
              const status = i === 0 ? 'done' : i === 1 ? 'active' : i < 4 ? 'done' : 'pending';
              const styles = {
                done:    { border: 'border-l-[var(--color-secondary)]',         icon: 'verified',  iconColor: 'text-[var(--color-secondary)]' },
                active:  { border: 'border-l-[var(--color-primary-container)]', icon: 'science',   iconColor: 'text-[var(--color-primary-container)]' },
                pending: { border: 'border-l-[var(--color-outline)]',           icon: 'pending',   iconColor: 'text-[var(--color-outline)]' },
              }[status];
              const isSelected = t.symbol === effective;
              return (
                <button
                  key={t.symbol}
                  onClick={() => setSelectedId(t.symbol)}
                  className={[
                    'relative text-left w-full bg-[var(--color-surface-container-high)] border border-l-4 border-[var(--color-outline-variant)] rounded p-2.5 transition-all',
                    styles.border,
                    isSelected ? 'pulse-cyan' : 'hover:border-opacity-80',
                    status === 'pending' ? 'opacity-50' : '',
                  ].join(' ')}
                >
                  <div className="flex justify-between items-start mb-0.5">
                    <span className={`font-mono text-xs font-semibold ${isSelected ? 'text-[var(--color-primary-container)]' : 'text-[var(--color-on-surface)]'}`}>
                      {t.symbol}
                    </span>
                    <span className={`material-symbols-outlined text-sm ${styles.iconColor}`}>{styles.icon}</span>
                  </div>
                  <div className="text-[10px] text-[var(--color-on-surface-variant)]">
                    {t.tdl} · score {t.aggregate_score.toFixed(3)}
                  </div>
                  {t.modality_secondary && (
                    <div className="text-[9px] text-[var(--color-outline)] mt-0.5">
                      +{t.modality_secondary}
                    </div>
                  )}
                  {(() => {
                    const p3 = ((t.evidence_trail as Record<string, unknown>)?.phase3 as Record<string, unknown> | undefined);
                    const priority = String(p3?.repurposing_priority ?? '');
                    if (!priority) return null;
                    const cls = priority === 'HIGH' ? 'text-[var(--color-secondary)]' : priority === 'MEDIUM' ? 'text-[var(--color-primary-container)]' : 'text-[var(--color-outline)]';
                    return <div className={`text-[9px] font-bold mt-0.5 ${cls}`}>{priority}</div>;
                  })()}
                  <div
                    className={`absolute w-2 h-2 rounded-full -right-1 top-1/2 -translate-y-1/2 ${
                      isSelected
                        ? 'bg-[var(--color-primary-container)] shadow-[0_0_8px_rgba(255,255,255,.8)]'
                        : 'bg-[var(--color-outline-variant)]'
                    }`}
                  />
                </button>
              );
            })}
          </div>

          {/* Center: decorative flow lines */}
          <div className="flex-1 relative h-full mx-2">
            <svg width="100%" height="100%" preserveAspectRatio="none" className="absolute inset-0">
              <defs>
                <linearGradient id="flowGrad3" x1="0" x2="1" y1="0" y2="0">
                  <stop offset="0%" stopColor="#ffffff" stopOpacity="0.6" />
                  <stop offset="100%" stopColor="#9e9e9e" stopOpacity="0.3" />
                </linearGradient>
              </defs>
              <path d="M 0 50  C 50 50,  50 30,  100 30"  fill="none" stroke="#3b494c"          strokeWidth="8"  strokeOpacity="0.4" />
              <path d="M 0 120 C 50 120, 50 80,  100 80"  fill="none" stroke="url(#flowGrad3)"  strokeWidth="14" strokeOpacity="0.8" />
              <path d="M 0 120 C 50 120, 50 160, 100 160" fill="none" stroke="url(#flowGrad3)"  strokeWidth="6"  strokeOpacity="0.8" />
              <path d="M 0 200 C 50 200, 50 210, 100 210" fill="none" stroke="#3b494c"          strokeWidth="10" strokeOpacity="0.3" strokeDasharray="4" />
              <path d="M 0 280 C 50 280, 50 40,  100 40"  fill="none" stroke="#3b494c"          strokeWidth="9"  strokeOpacity="0.4" />
            </svg>
          </div>

          {/* Right: modality buckets (real counts) */}
          <div className="w-52 space-y-3 flex flex-col justify-around h-full">
            {buckets.length > 0
              ? buckets.map(([label, count], i) => {
                  const meta = MODALITY_META[label] ?? MODALITY_META['Unknown'];
                  const active = i === 0;
                  return (
                    <div
                      key={label}
                      className={[
                        'bg-[var(--color-surface)] border rounded-lg overflow-hidden',
                        active
                          ? 'border-[var(--color-primary-container)]/50 shadow-[0_0_15px_rgba(255,255,255,.1)]'
                          : 'border-[var(--color-outline-variant)]',
                      ].join(' ')}
                    >
                      <div className={`px-3 py-2 flex justify-between items-center border-b border-[var(--color-outline-variant)] ${active ? 'bg-[var(--color-primary-container)]/10' : 'bg-[var(--color-surface-variant)]'}`}>
                        <span className="text-xs font-semibold text-[var(--color-on-surface)] truncate">{label}</span>
                        <span className={`font-mono text-[10px] font-bold ml-2 shrink-0 ${active ? 'text-[var(--color-primary-container)]' : 'text-[var(--color-outline)]'}`}>
                          n={count}
                        </span>
                      </div>
                      <div className="px-3 py-2 bg-[var(--color-surface-container-low)] relative">
                        {active && <div className="absolute left-0 top-0 w-1 h-full bg-[var(--color-primary-container)]/50" />}
                        <div className="flex justify-between text-[10px] text-[var(--color-on-surface-variant)] mb-1">
                          <span>{Math.round((count / targets.length) * 100)}% of targets</span>
                          <span style={{ color: meta.color }}>{meta.icon ? '' : ''}</span>
                        </div>
                        {active && (
                          <div className="w-full h-0.5 bg-[var(--color-surface-container-highest)] rounded-full overflow-hidden">
                            <div className="h-full bg-[var(--color-primary-container)]" style={{ width: `${(count / targets.length) * 100}%` }} />
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              : /* fallback if no modality data */
                ['Small Molecule', 'Biologic', 'PROTAC', 'Repurposing'].map((label) => (
                  <div key={label} className="bg-[var(--color-surface)] border border-[var(--color-outline-variant)] rounded-lg px-3 py-3 opacity-40">
                    <span className="text-xs text-[var(--color-on-surface-variant)]">{label}</span>
                    <span className="font-mono text-[10px] text-[var(--color-outline)] ml-2">n=0</span>
                  </div>
                ))}
          </div>
        </div>

        {/* Legend */}
        <div className="absolute bottom-4 right-4 flex gap-4 text-[10px] uppercase tracking-wider text-[var(--color-on-surface-variant)] font-bold">
          <div className="flex items-center gap-1.5"><span className="w-3 h-px bg-[#3b494c] block" /> Unassigned</div>
          <div className="flex items-center gap-1.5"><span className="w-3 h-px bg-[#ffffff] block" /> Active Flow</div>
        </div>
      </div>

      {/* P3 gate decision */}
      {p3Decision && (
        <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-5 relative">
          <div className="absolute top-0 left-0 w-1 h-full bg-[var(--color-primary-container)] rounded-l" />
          <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-primary-container)] mb-2 flex items-center gap-1">
            <span className="material-symbols-outlined text-sm">auto_awesome</span>
            Phoenix AI — Modality Gate ({p3Decision.gate})
          </p>
          <p className="text-sm text-[var(--color-on-surface)] leading-relaxed italic">
            {String((p3Decision.decision_json as Record<string, unknown>).rationale ?? JSON.stringify(p3Decision.decision_json))}
          </p>
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value, green }: { label: string; value: string; green?: boolean }) {
  return (
    <div className="bg-[var(--color-surface-container)] border border-[var(--color-outline-variant)] rounded-lg p-3 w-28 flex flex-col items-center">
      <span className="text-[10px] uppercase font-bold tracking-widest text-[var(--color-outline)] mb-1">{label}</span>
      <span className={`font-mono text-xl font-semibold ${green ? 'text-[var(--color-secondary)]' : 'text-[var(--color-on-surface)]'}`}>{value}</span>
    </div>
  );
}

import { useState } from 'react';
import { useAppStore } from '../store';
import { useCandidates } from '../hooks/useRuns';
import type { ApiCandidate } from '../lib/api';

const AA_COLOR: Record<string, string> = {
  K:'#ffffff', R:'#ffffff', H:'#9e9e9e',
  D:'#ff5555', E:'#ff5555',
  A:'#bac9cc', G:'#bac9cc', V:'#bac9cc', L:'#bac9cc', I:'#bac9cc', P:'#849396',
  F:'#d9c8ff', W:'#d9c8ff', Y:'#d0bcff', M:'#d0bcff',
  S:'#6ffbbe', T:'#6ffbbe', C:'#6ffbbe', N:'#6ffbbe', Q:'#6ffbbe',
};

function sub(c: ApiCandidate, key: string): unknown {
  return c.subscores?.[key];
}

function fmt(v: unknown, decimals = 2): string {
  const n = Number(v);
  return isNaN(n) || n === 0 ? '—' : n.toFixed(decimals);
}

const STRATEGY_BADGE: Record<string, { label: string; cls: string }> = {
  cyclic_peptide:   { label: 'Cyclic Peptide',  cls: 'bg-[#d0bcff]/15 text-[#d0bcff] border-[#d0bcff]/30' },
  antibody_epitope: { label: 'Antibody Epitope', cls: 'bg-[var(--color-secondary)]/15 text-[var(--color-secondary)] border-[var(--color-secondary)]/30' },
  helical_mimetic:  { label: 'Helical Mimetic',  cls: 'bg-[var(--color-primary-container)]/15 text-[var(--color-primary-container)] border-[var(--color-primary-container)]/30' },
  stapled_peptide:  { label: 'Stapled Peptide',  cls: 'bg-[#fbbf24]/15 text-[#fbbf24] border-[#fbbf24]/30' },
};

const AGG_COLOR: Record<string, string> = {
  low:    'text-[var(--color-secondary)]',
  medium: 'text-[#fbbf24]',
  high:   'text-[var(--color-error)]',
};

export default function Phase6Biologics() {
  const { activeRunId } = useAppStore();
  const { data: rawCandidates = [], isLoading } = useCandidates(activeRunId);
  const biologics = rawCandidates.filter((c) => c.kind === 'biologic');
  const [idx, setIdx] = useState(0);
  const [showFull, setShowFull] = useState(false);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="material-symbols-outlined text-4xl text-[var(--color-outline)] animate-spin">progress_activity</span>
      </div>
    );
  }

  if (biologics.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-[var(--color-on-surface-variant)]">
        <span className="material-symbols-outlined text-5xl">polymer</span>
        <p className="text-base font-semibold">No biologic candidates yet</p>
        <p className="text-sm">Phase 6 generates biologics when de_novo mode is enabled.</p>
      </div>
    );
  }

  const candidate = biologics[Math.min(idx, biologics.length - 1)];
  const seq = candidate.sequence ?? String(sub(candidate, 'sequence') ?? '');
  const displaySeq = showFull ? seq : seq.slice(0, 60);

  const iptm            = Number(sub(candidate, 'iptm') ?? 0);
  const paeInterface    = Number(sub(candidate, 'pae_interface') ?? 0);
  const designStrategy  = String(sub(candidate, 'design_strategy') ?? '');
  const length          = Number(sub(candidate, 'length') ?? seq.length ?? 0);
  const aggregation     = String(sub(candidate, 'aggregation') ?? '').toLowerCase();
  const stability       = (sub(candidate, 'stability') as Record<string, unknown> | undefined) ?? {};
  const halfLifeClass   = String(stability.half_life_class ?? '');
  const proteolysis     = Boolean(stability.proteolysis_concern ?? false);
  const disqualifying   = (sub(candidate, 'disqualifying') as string[] | undefined) ?? [];
  const concerns        = (sub(candidate, 'concerns') as string[] | undefined) ?? [];
  const immunRpt        = String(sub(candidate, 'immunogenicity_report') ?? '');

  const stratBadge = STRATEGY_BADGE[designStrategy];

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-end justify-between border-b border-[var(--color-outline-variant)] pb-3">
        <div>
          <h2 className="text-2xl font-bold text-[var(--color-on-surface)] mb-0.5">
            Biologic Candidate: {candidate.identifier}
          </h2>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className="text-[10px] px-2 py-0.5 bg-[var(--color-primary-container)]/15 border border-[var(--color-primary-container)]/30 rounded text-[var(--color-primary-container)] font-bold">
              {candidate.kind.toUpperCase()}
            </span>
            {stratBadge && (
              <span className={`text-[10px] px-2 py-0.5 border rounded font-bold ${stratBadge.cls}`}>
                {stratBadge.label}
              </span>
            )}
            {length > 0 && (
              <span className="text-[10px] px-2 py-0.5 bg-[var(--color-surface-container-high)] border border-[var(--color-outline-variant)] rounded text-[var(--color-on-surface-variant)]">
                {length} AA
              </span>
            )}
          </div>
        </div>

        {biologics.length > 1 && (
          <div className="flex items-center gap-1">
            {biologics.slice(0, 5).map((b, i) => (
              <button
                key={b.id}
                onClick={() => { setIdx(i); setShowFull(false); }}
                className={[
                  'px-2.5 py-1 rounded text-[11px] font-mono font-bold border transition-colors',
                  i === idx
                    ? 'bg-[var(--color-primary-container)] text-[var(--color-on-primary-container)] border-transparent'
                    : 'border-[var(--color-outline-variant)] text-[var(--color-on-surface-variant)] hover:border-[var(--color-outline)]',
                ].join(' ')}
              >
                {b.identifier.slice(0, 8)}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Left: real developability metrics */}
        <div className="col-span-4 space-y-3">
          <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-3">Binding & Structure</p>
            <div className="space-y-2">
              <MetricRow label="ipTM Score" value={iptm > 0 ? iptm.toFixed(3) : '—'} good={iptm >= 0.7} />
              {paeInterface > 0 && <MetricRow label="PAE Interface" value={`${paeInterface.toFixed(1)} Å`} good={paeInterface <= 5} />}
            </div>
          </div>

          <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-3">Developability</p>
            <div className="space-y-2">
              {aggregation && (
                <div className="flex justify-between text-xs">
                  <span className="text-[var(--color-on-surface-variant)]">Aggregation</span>
                  <span className={`font-semibold capitalize ${AGG_COLOR[aggregation] ?? 'text-[var(--color-on-surface)]'}`}>{aggregation}</span>
                </div>
              )}
              {halfLifeClass && (
                <div className="flex justify-between text-xs">
                  <span className="text-[var(--color-on-surface-variant)]">Half-life</span>
                  <span className="font-semibold capitalize text-[var(--color-on-surface)]">{halfLifeClass}</span>
                </div>
              )}
              <div className="flex justify-between text-xs">
                <span className="text-[var(--color-on-surface-variant)]">Proteolysis Risk</span>
                <span className={`font-semibold ${proteolysis ? 'text-[var(--color-error)]' : 'text-[var(--color-secondary)]'}`}>
                  {proteolysis ? 'Yes' : 'No'}
                </span>
              </div>
            </div>
          </div>

          {/* Pass/fail flags */}
          {(disqualifying.length > 0 || concerns.length > 0) && (
            <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-4">
              {disqualifying.length > 0 && (
                <>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-error)] mb-1">Disqualifying</p>
                  <ul className="space-y-0.5 mb-2">
                    {disqualifying.map((d) => (
                      <li key={d} className="text-xs text-[var(--color-error)] flex gap-1">
                        <span className="shrink-0">·</span>{d}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {concerns.length > 0 && (
                <>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-[#fbbf24] mb-1">Concerns</p>
                  <ul className="space-y-0.5">
                    {concerns.map((c) => (
                      <li key={c} className="text-xs text-[#fbbf24] flex gap-1">
                        <span className="shrink-0">·</span>{c}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}

          {/* Score ring */}
          <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-3">Combined Score</p>
            <div className="flex items-center gap-3">
              <div className="relative w-16 h-16 shrink-0">
                <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                  <circle cx="18" cy="18" r="15.9" fill="none" stroke="#3b494c" strokeWidth="3" />
                  <circle cx="18" cy="18" r="15.9" fill="none" stroke="#9e9e9e" strokeWidth="3"
                    strokeDasharray={`${candidate.combined_score * 100} 100`} strokeLinecap="round" />
                </svg>
                <span className="absolute inset-0 flex items-center justify-center font-mono text-xs font-bold text-[var(--color-secondary)]">
                  {(candidate.combined_score * 100).toFixed(0)}
                </span>
              </div>
              <div className="text-xs text-[var(--color-on-surface-variant)] leading-relaxed">
                {iptm > 0 ? 'ipTM 50% + Developability 50%' : 'Developability score (no structure validation)'}
              </div>
            </div>
          </div>
        </div>

        {/* Right: sequence + subscores */}
        <div className="col-span-8 space-y-4">
          {/* Sequence map */}
          <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">Sequence Map</p>
              <div className="flex items-center gap-3 text-[10px] text-[var(--color-on-surface-variant)]">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#ff5555]" /> Charged (D/E)</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#ffffff]" /> Basic (K/R)</span>
              </div>
            </div>
            {seq ? (
              <div className="bg-[var(--color-surface-container-lowest)] rounded-lg p-3 overflow-x-auto">
                <div className="flex flex-wrap gap-0.5">
                  {displaySeq.split('').map((aa, i) => (
                    <div key={i} className="flex flex-col items-center">
                      <div
                        className="w-6 h-6 rounded flex items-center justify-center font-mono text-[9px] font-bold bg-[var(--color-surface-container-high)]"
                        style={{ color: AA_COLOR[aa] ?? '#bac9cc' }}
                      >
                        {aa}
                      </div>
                    </div>
                  ))}
                  {!showFull && seq.length > 60 && (
                    <button
                      onClick={() => setShowFull(true)}
                      className="font-mono text-[9px] text-[var(--color-primary-container)] hover:underline px-2 self-end"
                    >
                      +{seq.length - 60} more
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-xs text-[var(--color-on-surface-variant)] italic">No sequence available.</p>
            )}
          </div>

          {/* Immunogenicity report if present */}
          {immunRpt && (
            <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-4 relative">
              <div className="absolute top-0 left-0 w-1 h-full bg-[#fbbf24] rounded-l" />
              <p className="text-[10px] font-bold uppercase tracking-widest text-[#fbbf24] mb-2 flex items-center gap-1 ml-2">
                <span className="material-symbols-outlined text-xs">biotech</span> Immunogenicity Assessment
              </p>
              <p className="text-xs text-[var(--color-on-surface)] leading-relaxed ml-2">{immunRpt}</p>
            </div>
          )}

          {/* Subscores table */}
          {Object.keys(candidate.subscores ?? {}).length > 0 && (
            <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-[var(--color-outline-variant)] flex items-center justify-between bg-[var(--color-surface-container-high)]">
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">All Subscores</p>
              </div>
              <table className="w-full text-left">
                <tbody className="divide-y divide-[var(--color-outline-variant)]">
                  {Object.entries(candidate.subscores ?? {})
                    .filter(([, v]) => typeof v !== 'object' || v === null)
                    .map(([k, v]) => (
                      <tr key={k} className="hover:bg-[var(--color-surface-container-high)] transition-colors">
                        <td className="px-4 py-2.5 text-xs text-[var(--color-on-surface-variant)] capitalize">{k.replace(/_/g, ' ')}</td>
                        <td className="px-4 py-2.5 font-mono text-xs text-[var(--color-primary-container)]">
                          {typeof v === 'number' ? (v as number).toFixed(4) : String(v)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricRow({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-[var(--color-on-surface-variant)]">{label}</span>
      <span className={`font-mono font-semibold ${good ? 'text-[var(--color-secondary)]' : good === false ? 'text-[var(--color-error)]' : 'text-[var(--color-on-surface)]'}`}>
        {value}
      </span>
    </div>
  );
}

import { useState } from 'react';
import { useAppStore } from '../store';
import { useCandidates } from '../hooks/useRuns';

interface Molecule {
  id: string;
  smiles: string;
  qed: number;
  sa: number;
  mw: number;
  logP: number;
  lipinski: boolean;
  dockScore: number;
  admetScore: number;
  novelty: number;
  passed: boolean;
  method: 'REINVENT4' | 'BRICS' | 'Unknown';
  admet: Record<string, unknown>;
  narrative: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function candidateToMolecule(c: any): Molecule {
  const sub = (c?.subscores ?? {}) as Record<string, unknown>;
  const admet = (sub.admet ?? {}) as Record<string, unknown>;
  return {
    id: String(c?.identifier ?? c?.id ?? ''),
    smiles: String(c?.smiles ?? ''),
    qed: Number(sub.qed ?? 0),
    sa: Number(sub.sa_score ?? sub.sa ?? 0),
    mw: Number(sub.mw ?? 0),
    logP: Number(sub.logP ?? 0),
    lipinski: Boolean(sub.lipinski ?? true),
    dockScore: Number(sub.vina_score ?? sub.vina ?? c?.combined_score ?? 0),
    admetScore: Number(sub.admet_score ?? 0),
    novelty: Number(sub.novelty ?? 0),
    passed: Boolean(sub.passed ?? false),
    method: (['REINVENT4', 'BRICS'].includes(String(sub.method)) ? sub.method : 'Unknown') as Molecule['method'],
    admet,
    narrative: String(sub.narrative ?? ''),
  };
}

const HERG_COLOR: Record<string, string> = {
  low:    'bg-[var(--color-secondary)]/20 text-[var(--color-secondary)] border-[var(--color-secondary)]/30',
  medium: 'bg-[#fbbf24]/20 text-[#fbbf24] border-[#fbbf24]/30',
  high:   'bg-[var(--color-error)]/20 text-[var(--color-error)] border-[var(--color-error)]/30',
};

export default function Phase5DeNovoSM() {
  const { activeRunId } = useAppStore();
  const { data: rawCandidates = [] } = useCandidates(activeRunId);
  const molecules: Molecule[] = rawCandidates
    .filter((c) => c.kind === 'sm' || c.kind === 'de_novo_sm')
    .map(candidateToMolecule);
  const [selected, setSelected] = useState<Molecule | null>(null);
  const effectiveSelected = selected ?? molecules[0] ?? null;
  const [filter, setFilter] = useState<'All' | 'REINVENT4' | 'BRICS'>('All');

  const visible = filter === 'All' ? molecules : molecules.filter((m) => m.method === filter);

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-end justify-between border-b border-[var(--color-outline-variant)] pb-3">
        <div>
          <h2 className="text-2xl font-bold text-[var(--color-on-surface)] mb-0.5">Generated Candidates</h2>
          <p className="text-sm text-[var(--color-on-surface-variant)]">
            {molecules.length} compound{molecules.length !== 1 ? 's' : ''} generated via SM/Scaffold ·{' '}
            {molecules.filter((m) => m.passed).length} passed all gates
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1 bg-[var(--color-surface-container-high)] p-1 rounded-lg border border-[var(--color-outline-variant)]">
            {(['All', 'REINVENT4', 'BRICS'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={[
                  'px-3 py-1 rounded text-[11px] font-bold transition-colors',
                  filter === f
                    ? 'bg-[var(--color-primary-container)] text-[var(--color-on-primary-container)]'
                    : 'text-[var(--color-on-surface-variant)] hover:text-[var(--color-on-surface)]',
                ].join(' ')}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      </div>

      {molecules.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-[var(--color-on-surface-variant)]">
          <span className="material-symbols-outlined text-5xl">science</span>
          <p className="text-base font-semibold">No de novo candidates yet</p>
          <p className="text-sm">Phase 5 generates small molecules when de_novo mode is enabled.</p>
        </div>
      ) : (
        <>
          {/* Molecule grid */}
          <div className="grid grid-cols-3 gap-3">
            {visible.map((mol) => (
              <MolCard
                key={mol.id}
                mol={mol}
                selected={effectiveSelected?.id === mol.id}
                onClick={() => setSelected(mol)}
              />
            ))}
          </div>

          {/* Selected detail panel */}
          {effectiveSelected && (
            <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-high)]">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm font-bold text-[var(--color-primary-container)]">{effectiveSelected.id}</span>
                  <span className="text-[10px] px-1.5 py-0.5 border border-[var(--color-outline-variant)] rounded text-[var(--color-on-surface-variant)]">
                    {effectiveSelected.method}
                  </span>
                  {effectiveSelected.passed && (
                    <span className="text-[9px] px-1.5 py-0.5 bg-[var(--color-secondary)]/20 border border-[var(--color-secondary)]/30 rounded text-[var(--color-secondary)] font-bold">PASS</span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 divide-x divide-[var(--color-outline-variant)]">
                {/* SMILES */}
                <div className="p-4">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)] mb-2">SMILES</p>
                  <div className="bg-[var(--color-surface-container-lowest)] border border-[var(--color-outline-variant)]/40 rounded p-3">
                    <p className="font-mono text-[11px] text-[var(--color-on-surface-variant)] break-all leading-relaxed">
                      {effectiveSelected.smiles || '—'}
                    </p>
                  </div>
                </div>

                {/* Properties */}
                <div className="p-4">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)] mb-2">Properties</p>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { label: 'QED',    value: effectiveSelected.qed.toFixed(3),     accent: effectiveSelected.qed >= 0.6 },
                      { label: 'SA',     value: effectiveSelected.sa.toFixed(2),      accent: false },
                      { label: 'MW',     value: `${effectiveSelected.mw.toFixed(0)}`, accent: false },
                      { label: 'logP',   value: effectiveSelected.logP.toFixed(1),    accent: false },
                      { label: 'Vina',   value: `${effectiveSelected.dockScore.toFixed(1)}`, accent: effectiveSelected.dockScore <= -7 },
                      { label: 'ADMET',  value: effectiveSelected.admetScore > 0 ? effectiveSelected.admetScore.toFixed(3) : '—', accent: effectiveSelected.admetScore >= 0.6 },
                      { label: 'Novelty',value: effectiveSelected.novelty > 0 ? effectiveSelected.novelty.toFixed(3) : '—', accent: effectiveSelected.novelty >= 0.5 },
                      { label: 'Ro5',    value: effectiveSelected.lipinski ? '✓ Pass' : '✗ Fail', accent: effectiveSelected.lipinski },
                    ].map(({ label, value, accent }) => (
                      <div key={label} className="bg-[var(--color-surface-container)] border border-[var(--color-outline-variant)] rounded p-2 text-center">
                        <p className="text-[9px] font-bold uppercase tracking-widest text-[var(--color-outline)] mb-0.5">{label}</p>
                        <p className={`font-mono text-xs font-semibold ${accent ? 'text-[var(--color-secondary)]' : 'text-[var(--color-on-surface)]'}`}>{value}</p>
                      </div>
                    ))}
                  </div>

                  {/* ADMET flags row */}
                  <div className="flex gap-1.5 mt-2 flex-wrap">
                    {['hERG', 'AMES', 'BBB', 'hepatox'].map((key) => {
                      const val = String(effectiveSelected.admet?.[key] ?? '');
                      if (!val) return null;
                      let cls = 'bg-[var(--color-surface-container)] text-[var(--color-on-surface-variant)] border-[var(--color-outline-variant)]';
                      if (key === 'hERG') cls = HERG_COLOR[val.toLowerCase()] ?? cls;
                      if (key === 'AMES' && val === 'pos') cls = 'bg-[var(--color-error)]/20 text-[var(--color-error)] border-[var(--color-error)]/30';
                      if (key === 'AMES' && val === 'neg') cls = 'bg-[var(--color-secondary)]/20 text-[var(--color-secondary)] border-[var(--color-secondary)]/30';
                      if (key === 'BBB' && val === 'pos') cls = 'bg-[var(--color-primary-container)]/20 text-[var(--color-primary-container)] border-[var(--color-primary-container)]/30';
                      return (
                        <span key={key} className={`text-[9px] font-bold uppercase tracking-wider border px-1.5 py-0.5 rounded ${cls}`}>
                          {key} {val}
                        </span>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* LLM narrative */}
              {effectiveSelected.narrative && (
                <div className="px-5 py-4 border-t border-[var(--color-outline-variant)] relative">
                  <div className="absolute top-0 left-0 w-1 h-full bg-[var(--color-secondary)] rounded-l" />
                  <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-2 flex items-center gap-1 ml-2">
                    <span className="material-symbols-outlined text-xs">auto_awesome</span> AI Optimization Narrative
                  </p>
                  <p className="text-sm text-[var(--color-on-surface)] leading-relaxed ml-2">{effectiveSelected.narrative}</p>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function MolCard({ mol, selected, onClick }: { mol: Molecule; selected: boolean; onClick: () => void }) {
  const qedBand = mol.qed > 0.75 ? 'text-[var(--color-secondary)]' : mol.qed > 0.6 ? 'text-[var(--color-primary-container)]' : 'text-[var(--color-on-surface-variant)]';
  const herg = String(mol.admet?.hERG ?? '');
  const ames = String(mol.admet?.AMES ?? '');
  return (
    <button
      onClick={onClick}
      className={[
        'text-left rounded-xl border transition-all overflow-hidden group',
        selected
          ? 'border-[var(--color-primary-container)] bg-[var(--color-surface-container-high)]'
          : 'border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)] hover:bg-[var(--color-surface-container-high)] hover:border-[var(--color-outline)]',
      ].join(' ')}
    >
      {/* 2D structure placeholder */}
      <div className="relative w-full h-28 bg-[var(--color-surface-container-lowest)] overflow-hidden flex items-center justify-center">
        <div className="absolute inset-0" style={{
          backgroundImage: `radial-gradient(circle at 30% 40%, rgba(255,255,255,0.08) 0%, transparent 50%), radial-gradient(circle at 70% 60%, rgba(158,158,158,0.06) 0%, transparent 50%)`,
        }} />
        <svg width="100%" height="100%" className="absolute inset-0 opacity-20">
          {[0,1,2].map(row => [0,1,2,3].map(col => (
            <polygon
              key={`${row}-${col}`}
              points="20,0 40,0 50,17 40,34 20,34 10,17"
              transform={`translate(${col * 48 + (row % 2) * 24 - 10}, ${row * 30 - 5})`}
              fill="none" stroke="#3b494c" strokeWidth="0.5"
            />
          )))}
        </svg>
        <div className="z-10 text-center px-2">
          <p className="font-mono text-[10px] text-[var(--color-primary-container)] font-bold">{mol.id}</p>
          <p className="font-mono text-[9px] text-[var(--color-on-surface-variant)] mt-0.5 truncate max-w-full">
            {mol.smiles.length > 24 ? mol.smiles.slice(0, 24) + '…' : mol.smiles}
          </p>
        </div>
        <div className="absolute top-2 right-2 flex gap-1">
          {mol.passed && <span className="text-[8px] px-1 py-0.5 bg-[var(--color-secondary)]/20 text-[var(--color-secondary)] border border-[var(--color-secondary)]/30 rounded font-bold">✓</span>}
          <span className="text-[9px] px-1.5 py-0.5 bg-[var(--color-surface-container-high)]/80 border border-[var(--color-outline-variant)] rounded text-[var(--color-on-surface-variant)]">
            {mol.method}
          </span>
        </div>
      </div>

      {/* Scores row */}
      <div className="px-3 py-2.5 flex items-center justify-between">
        <div className="text-center">
          <p className="text-[9px] font-bold uppercase text-[var(--color-outline)]">QED</p>
          <p className={`font-mono text-sm font-bold ${qedBand}`}>{mol.qed.toFixed(2)}</p>
        </div>
        <div className="w-px h-6 bg-[var(--color-outline-variant)]" />
        <div className="text-center">
          <p className="text-[9px] font-bold uppercase text-[var(--color-outline)]">Vina</p>
          <p className="font-mono text-sm font-bold text-[var(--color-secondary)]">{mol.dockScore.toFixed(1)}</p>
        </div>
        <div className="w-px h-6 bg-[var(--color-outline-variant)]" />
        <div className="text-center">
          <p className="text-[9px] font-bold uppercase text-[var(--color-outline)]">ADMET</p>
          <p className="font-mono text-sm text-[var(--color-on-surface)]">{mol.admetScore > 0 ? mol.admetScore.toFixed(2) : '—'}</p>
        </div>
      </div>

      {/* ADMET flags */}
      {(herg || ames) && (
        <div className="px-3 pb-2 flex gap-1 flex-wrap">
          {herg && (
            <span className={`text-[8px] font-bold border px-1 py-0.5 rounded ${HERG_COLOR[herg.toLowerCase()] ?? 'bg-[var(--color-surface-container)] text-[var(--color-on-surface-variant)] border-[var(--color-outline-variant)]'}`}>
              hERG {herg}
            </span>
          )}
          {ames && (
            <span className={`text-[8px] font-bold border px-1 py-0.5 rounded ${ames === 'pos' ? 'bg-[var(--color-error)]/20 text-[var(--color-error)] border-[var(--color-error)]/30' : 'bg-[var(--color-secondary)]/20 text-[var(--color-secondary)] border-[var(--color-secondary)]/30'}`}>
              AMES {ames}
            </span>
          )}
        </div>
      )}
    </button>
  );
}

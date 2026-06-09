import { useAppStore } from '../store';
import { useTargets } from '../hooks/useRuns';
import { useRunStream } from '../hooks/useRunStream';
import type { ApiTarget } from '../lib/api';

function exprBand(trail: Record<string, unknown>): 'High' | 'Med' | 'Low' | 'V.High' {
  const v = Number(trail?.expression ?? 0);  // log1p(TPM) from backend
  if (v > 5.0) return 'V.High';  // ≈ raw TPM > 148
  if (v > 4.0) return 'High';    // ≈ raw TPM > 53
  if (v > 2.5) return 'Med';     // ≈ raw TPM > 11
  return 'Low';
}

const EXPR_COLOR: Record<string, string> = {
  High:   'var(--color-secondary)',
  Med:    'var(--color-primary-container)',
  Low:    'var(--color-on-surface-variant)',
  'V.High': 'var(--color-error)',
};
const EXPR_W: Record<string, string> = {
  High: '70%', Med: '50%', Low: '25%', 'V.High': '92%',
};

function geneticBand(score: number): string {
  if (score >= 0.7) return 'text-[var(--color-secondary)]';
  if (score >= 0.4) return 'text-[var(--color-primary-container)]';
  return 'text-[var(--color-on-surface-variant)]';
}

export default function Phase1TargetID() {
  const { activeRunId, selectedTarget, setSelectedTarget, setInspectorOpen } = useAppStore();

  useRunStream(activeRunId);

  const { data: targets = [], isLoading, error } = useTargets(activeRunId);

  function handleRow(t: ApiTarget) {
    setSelectedTarget(t);
    setInspectorOpen(true);
  }

  if (!activeRunId) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--color-on-surface-variant)]">
        <p className="text-sm">Select or start a run from the sidebar.</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--color-on-surface-variant)]">
        <span className="material-symbols-outlined animate-spin mr-2">progress_activity</span>
        <p className="text-sm">Loading targets…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--color-error)]">
        <p className="text-sm">Failed to load targets: {String(error)}</p>
      </div>
    );
  }

  if (targets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-[var(--color-on-surface-variant)] gap-3">
        <span className="material-symbols-outlined text-4xl">hourglass_empty</span>
        <p className="text-sm">Phase 1 is still running — targets will appear here once ranked.</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between border-b border-[var(--color-outline-variant)] pb-4">
        <div>
          <h2 className="text-3xl font-bold text-[var(--color-on-surface)] mb-1">Top Candidate Targets</h2>
          <p className="text-sm text-[var(--color-on-surface-variant)]">
            {targets.length} targets · Prioritized by PU-learning on 14 omics features.
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs text-[var(--color-on-surface-variant)]">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[var(--color-secondary)]" /> High Confidence
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[var(--color-error)]" /> Toxicity Warning
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="bg-[var(--color-surface-container-low)] rounded-lg overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-[var(--color-surface-container)] border-b border-[var(--color-outline-variant)]">
              {['Rank', 'HGNC Symbol', 'PU Score', 'Genetic ⓘ', 'TDL', 'GTEx Expression', 'Val. Score ⓘ', ''].map((h) => (
                <th
                  key={h}
                  className="py-3 px-4 text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]"
                  title={
                    h === 'Genetic ⓘ' ? 'Combined GWAS + OMIM + DISEASES score — human genetic validation signal' :
                    h === 'Val. Score ⓘ' ? 'Phase 2 druggability validation score — populated after Phase 2 completes' :
                    undefined
                  }
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="font-mono text-[13px] text-[var(--color-on-surface)] divide-y divide-[var(--color-outline-variant)]">
            {targets.map((t) => {
              const isSelected = selectedTarget?.symbol === t.symbol;
              const expr = exprBand(t.evidence_trail);
              const highTox = Boolean((t.evidence_trail as { val_critical_tissue?: boolean })?.val_critical_tissue);
              const genetic = Number((t.evidence_trail as Record<string, unknown>)?.genetic ?? -1);
              const hasGenetic = genetic >= 0;

              return (
                <tr
                  key={t.rank}
                  onClick={() => handleRow(t)}
                  className={[
                    'cursor-pointer transition-colors hover:bg-[var(--color-surface-container-high)]',
                    isSelected ? 'bg-[var(--color-surface-container-highest)] border-l-2 border-l-[var(--color-primary-container)]' : '',
                    highTox ? 'hover:bg-[var(--color-error-container)]/10' : '',
                  ].join(' ')}
                >
                  <td className="py-3 px-4 text-[var(--color-on-surface-variant)]">
                    {String(t.rank).padStart(2, '0')}
                    {t.seeded && (
                      <span className="ml-1 text-[var(--color-primary-container)]" title="Seeded">★</span>
                    )}
                  </td>
                  <td className="py-3 px-4">
                    <span className={isSelected ? 'text-[var(--color-primary-container)] font-bold' : highTox ? 'text-[var(--color-error)]' : ''}>
                      {t.symbol}
                    </span>
                  </td>
                  <td className="py-3 px-4">{t.aggregate_score.toFixed(3)}</td>
                  <td className="py-3 px-4">
                    {hasGenetic
                      ? <span className={geneticBand(genetic)}>{genetic.toFixed(3)}</span>
                      : <span className="text-[var(--color-on-surface-variant)] text-[11px]">—</span>
                    }
                  </td>
                  <td className="py-3 px-4">
                    <span className="text-[11px] px-1.5 py-0.5 rounded bg-[var(--color-surface-container)] text-[var(--color-on-surface-variant)]">
                      {t.tdl ?? '—'}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1 bg-[var(--color-surface-container)] rounded overflow-hidden">
                        <div
                          className="h-full rounded"
                          style={{ width: EXPR_W[expr], backgroundColor: EXPR_COLOR[expr] }}
                        />
                      </div>
                      <span className="text-[11px]" style={{ color: EXPR_COLOR[expr] }}>{expr}</span>
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    {t.validation_score != null
                      ? <span className={t.validation_score >= 0.5 ? 'text-[var(--color-secondary)]' : 'text-[var(--color-on-surface-variant)]'}>
                          {t.validation_score.toFixed(3)}
                        </span>
                      : <span
                          className="text-[var(--color-on-surface-variant)] text-[11px] cursor-help border-b border-dashed border-[var(--color-outline-variant)]"
                          title="Populated after Phase 2 druggability validation completes"
                        >
                          —
                        </span>
                    }
                  </td>
                  <td className="py-3 px-4 text-right">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRow(t); }}
                      className="inline-flex items-center gap-1 px-2 py-1 border border-[var(--color-outline-variant)] rounded text-[10px] text-[var(--color-on-surface-variant)] hover:border-[var(--color-primary-container)] hover:text-[var(--color-primary-container)] transition-colors"
                    >
                      <span className="material-symbols-outlined text-xs">troubleshoot</span>
                      Why?
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Bento grid placeholders */}
      <div className="grid grid-cols-2 gap-4">
        <BentoPlaceholder title="Pathway Enrichment" gradient="radial-gradient(ellipse at center, rgba(255,255,255,.08) 0%, transparent 70%)" />
        <BentoPlaceholder title="Expression Heatmap" gradient="conic-gradient(at top right, rgba(158,158,158,.08), transparent, rgba(255,85,85,.08))" />
      </div>
    </div>
  );
}

function BentoPlaceholder({ title, gradient }: { title: string; gradient: string }) {
  return (
    <div className="bg-[var(--color-surface-container-low)] rounded-lg p-4 h-56 flex flex-col">
      <h4 className="text-sm font-semibold text-[var(--color-on-surface)] mb-3">{title}</h4>
      <div className="flex-1 border border-[var(--color-outline-variant)]/30 rounded flex items-center justify-center relative overflow-hidden">
        <div className="absolute inset-0" style={{ background: gradient }} />
        <span className="font-mono text-[11px] text-[var(--color-on-surface-variant)] z-10">
          [Requires additional backend computation]
        </span>
      </div>
    </div>
  );
}

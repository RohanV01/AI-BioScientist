import { useAppStore } from '../store';
import { useTargets } from '../hooks/useRuns';
import type { ApiTarget } from '../lib/api';

const STATUS_CFG = {
  Validated:    { color: 'var(--color-secondary)',         dot: 'bg-[#9e9e9e]',  pulse: true  },
  Processing:   { color: 'var(--color-primary-container)', dot: 'bg-[#ffffff]',  pulse: true  },
  Insignificant:{ color: 'var(--color-error)',             dot: 'bg-[#ff5555]',  pulse: false },
};

type RowStatus = 'Validated' | 'Processing' | 'Insignificant';

interface ValidationRow {
  symbol: string;
  validationScore: number;
  pocketScore: number;
  plddt: number;
  status: RowStatus;
  localization: string;
  passed: boolean;
  evidenceSummary: string;
}

function toRow(t: ApiTarget): ValidationRow {
  const trail = t.evidence_trail ?? {};
  const p2 = (trail.phase2 as Record<string, unknown> | undefined) ?? {};
  const score = Number(t.validation_score ?? 0);
  const locData = p2.localization as Record<string, unknown> | undefined;
  const localization = String(locData?.compartment ?? locData?.subcellular_location ?? '—');
  const passed = Boolean(p2.passed ?? score >= 0.5);
  const evidenceSummary = String(p2.evidence_summary ?? '');
  return {
    symbol: t.symbol,
    validationScore: score,
    pocketScore: Number(p2.max_druggability ?? 0) * 100,
    plddt: Number((p2.structure as Record<string, unknown> | undefined)?.median_plddt ?? 0),
    status: score >= 0.7 ? 'Validated' : score >= 0.5 ? 'Processing' : 'Insignificant',
    localization,
    passed,
    evidenceSummary,
  };
}

const LOC_BADGE: Record<string, { label: string; cls: string }> = {
  intracellular: { label: 'Intracellular', cls: 'bg-[var(--color-primary-container)]/15 text-[var(--color-primary-container)] border-[var(--color-primary-container)]/30' },
  membrane:      { label: 'Membrane',      cls: 'bg-[#d0bcff]/15 text-[#d0bcff] border-[#d0bcff]/30' },
  secreted:      { label: 'Secreted',      cls: 'bg-[var(--color-secondary)]/15 text-[var(--color-secondary)] border-[var(--color-secondary)]/30' },
  extracellular: { label: 'Extracellular', cls: 'bg-[var(--color-secondary)]/15 text-[var(--color-secondary)] border-[var(--color-secondary)]/30' },
};

export default function Phase2Validation() {
  const { activeRunId } = useAppStore();
  const { data: rawTargets = [] } = useTargets(activeRunId);

  const p2Targets = rawTargets.filter((t) => t.validation_score != null);
  const rows: ValidationRow[] = p2Targets.map(toRow);

  const nValidated = rows.length;
  const nPassed    = rows.filter((r) => r.passed).length;
  const meanScore  = nValidated > 0
    ? rows.reduce((s, r) => s + r.validationScore, 0) / nValidated
    : 0;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Stats bento */}
      <div className="grid grid-cols-12 gap-4 mb-2">
        <div className="col-span-8 bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-6 relative overflow-hidden">
          <h3 className="text-lg font-semibold mb-1">Target Validation Suite</h3>
          <p className="text-sm text-[var(--color-on-surface-variant)] max-w-lg">
            Multi-axis druggability assessment: pocket geometry, expression safety, essentiality, and chemical precedent.
          </p>
          <div className="mt-5 flex gap-6">
            <StatBox
              label="Validated Targets"
              value={nValidated > 0 ? String(nValidated) : '—'}
              accent
            />
            <div className="w-px h-10 bg-[var(--color-outline-variant)]" />
            <StatBox
              label="Pass Rate"
              value={nValidated > 0 ? `${Math.round((nPassed / nValidated) * 100)}%` : '—'}
              green
            />
            <div className="w-px h-10 bg-[var(--color-outline-variant)]" />
            <StatBox
              label="Mean Val. Score"
              value={nValidated > 0 ? (meanScore * 100).toFixed(1) + '%' : '—'}
            />
          </div>
          <div className="absolute right-4 top-4 opacity-10">
            <span className="material-symbols-outlined text-[100px] text-[var(--color-primary-container)]">dns</span>
          </div>
        </div>
        <div className="col-span-4 bg-[var(--color-surface-container-high)] border-l1 rounded-xl p-6 flex flex-col justify-between">
          <div className="flex justify-between items-start">
            <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">Pass Threshold</span>
            <span className="bg-[var(--color-secondary-container)]/20 text-[var(--color-secondary)] px-2 py-0.5 rounded text-[10px] font-bold">
              {nPassed > 0 ? 'READY' : 'PENDING'}
            </span>
          </div>
          <div>
            <div className="flex items-center justify-between mb-1 text-xs font-mono">
              <span>{nPassed} of {nValidated} targets passed</span>
              <span className="text-[var(--color-primary-container)]">
                {nValidated > 0 ? Math.round((nPassed / nValidated) * 100) : 0}%
              </span>
            </div>
            <div className="h-1 bg-[var(--color-outline-variant)] rounded-full overflow-hidden">
              <div
                className="h-full bg-[var(--color-primary-container)]"
                style={{ width: `${nValidated > 0 ? (nPassed / nValidated) * 100 : 0}%` }}
              />
            </div>
          </div>
          <p className="text-[10px] text-[var(--color-on-surface-variant)] mt-2">
            Score ≥ 0.50 passes. Seeded targets always pass.
          </p>
        </div>
      </div>

      {/* Leaderboard table */}
      <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-[var(--color-outline-variant)] flex justify-between items-center bg-[var(--color-surface-container-high)]">
          <span className="font-semibold">Validation Leaderboard</span>
          <span className="text-[10px] text-[var(--color-on-surface-variant)] font-mono">
            {nPassed} passed · {nValidated - nPassed} failed · threshold 0.50
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-[var(--color-surface-container-highest)]/30">
                {['Target', 'Localization', 'Val. Score', 'Pocket Drugg.', 'pLDDT', 'Status', 'Pass'].map((h, i) => (
                  <th key={i} className="px-5 py-3.5 text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-outline-variant)]">
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-5 py-8 text-center text-sm text-[var(--color-on-surface-variant)]">
                    Phase 2 hasn't run yet — validation scores will appear here.
                  </td>
                </tr>
              ) : rows.map((r) => {
                const cfg = STATUS_CFG[r.status];
                const scoreColor = r.validationScore < 0.5 ? 'text-[var(--color-error)]' : 'text-[var(--color-secondary)]';
                const plddtColor = r.plddt < 50 ? 'text-[var(--color-error)]' : 'text-[var(--color-primary)]';
                const locBadge = LOC_BADGE[r.localization.toLowerCase()];
                return (
                  <tr key={r.symbol} className="hover:bg-[var(--color-surface-container-high)] transition-colors group cursor-pointer">
                    <td className="px-5 py-4">
                      <div className="font-mono text-sm text-[var(--color-primary-container)]">{r.symbol}</div>
                      {r.evidenceSummary && (
                        <div className="text-[10px] text-[var(--color-on-surface-variant)] mt-0.5 max-w-[160px] truncate" title={r.evidenceSummary}>
                          {r.evidenceSummary}
                        </div>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      {locBadge
                        ? <span className={`text-[9px] font-bold uppercase tracking-wider border px-1.5 py-0.5 rounded ${locBadge.cls}`}>
                            {locBadge.label}
                          </span>
                        : <span className="text-[11px] text-[var(--color-on-surface-variant)]">{r.localization}</span>
                      }
                    </td>
                    <td className="px-5 py-4 font-mono text-sm text-right">
                      <span className={scoreColor}>{r.validationScore.toFixed(3)}</span>
                    </td>
                    <td className="px-5 py-4 font-mono text-sm text-right">{r.pocketScore.toFixed(1)}</td>
                    <td className="px-5 py-4 font-mono text-sm text-right">
                      <span className={plddtColor}>{r.plddt > 0 ? r.plddt.toFixed(1) : '—'}</span>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2">
                        <span className={`h-2 w-2 rounded-full ${cfg.dot} ${cfg.pulse ? 'animate-pulse' : ''}`} />
                        <span className="text-xs" style={{ color: cfg.color }}>{r.status}</span>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <span className={`material-symbols-outlined text-base ${r.passed ? 'text-[var(--color-secondary)]' : 'text-[var(--color-outline)]'}`}
                        style={{ fontVariationSettings: "'FILL' 1" }}>
                        {r.passed ? 'check_circle' : 'cancel'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StatBox({ label, value, accent, green }: { label: string; value: string; accent?: boolean; green?: boolean }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-0.5">{label}</span>
      <span className={`font-mono text-xl font-semibold ${accent ? 'text-[var(--color-primary-container)]' : green ? 'text-[var(--color-secondary)]' : 'text-[var(--color-on-surface)]'}`}>{value}</span>
    </div>
  );
}

import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { useAppStore } from '../store';
import { useCandidates } from '../hooks/useRuns';
import type { ApiCandidate } from '../lib/api';

interface LeadRow {
  id: string;
  smiles: string;
  paretoRank: number | null;
  desirability: number;
  potency: number;
  admetScore: number;
  novelty: number;
  isPareto: boolean;
}

function toLeadRow(c: ApiCandidate): LeadRow {
  const sub = c.subscores ?? {};
  const paretoRank = sub.pareto_rank != null ? Number(sub.pareto_rank) : null;
  return {
    id: c.identifier || c.id,
    smiles: c.smiles ?? '—',
    paretoRank,
    desirability: Number(sub.desirability ?? c.combined_score),
    potency: Number(sub.potency ?? sub.vina_norm ?? 0),
    admetScore: Number(sub.admet_score ?? 0),
    novelty: Number(sub.novelty ?? 0),
    isPareto: paretoRank != null,
  };
}

export default function Phase7MPO() {
  const { activeRunId } = useAppStore();
  const { data: rawCandidates = [], isLoading } = useCandidates(activeRunId);

  const allLeads: LeadRow[] = rawCandidates
    .filter((c) => c.kind === 'sm' || c.kind === 'biologic' || c.kind === 'de_novo_sm')
    .sort((a, b) => b.combined_score - a.combined_score)
    .slice(0, 12)
    .map(toLeadRow);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="material-symbols-outlined text-4xl text-[var(--color-outline)] animate-spin">progress_activity</span>
      </div>
    );
  }

  const paretoCount = allLeads.filter((l) => l.isPareto).length;
  const candidateCount = rawCandidates.length;

  // Build scatter data: admet_score vs potency (both 0–1)
  const scatterData = allLeads.map((l) => ({
    admet: l.admetScore,
    potency: l.potency,
    id: l.id,
    pareto: l.isPareto,
  }));

  const hasRealData = allLeads.some((l) => l.admetScore > 0 || l.potency > 0);

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-end justify-between border-b border-[var(--color-outline-variant)] pb-3">
        <div>
          <h2 className="text-2xl font-bold text-[var(--color-on-surface)] mb-0.5">Multi-Parameter Optimization (MPO)</h2>
          <p className="text-sm text-[var(--color-on-surface-variant)]">
            {candidateCount > 0
              ? `${candidateCount} candidates · Pareto front by Bayesian optimization (potency × ADMET × novelty)`
              : 'No candidates yet — requires Phase 5/6 to complete first.'}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#ffffff] shadow-[0_0_6px_rgba(255,255,255,.6)]" />
            <span className="text-[var(--color-on-surface-variant)]">Pareto front</span>
          </span>
          <span className="flex items-center gap-1.5 ml-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#333539] border border-[#3b494c]" />
            <span className="text-[var(--color-on-surface-variant)]">Sub-optimal</span>
          </span>
        </div>
      </div>

      {/* Pareto scatter (real data) */}
      <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-5">
        <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-1">
          Objective Space
        </p>
        <p className="text-xs text-[var(--color-on-surface-variant)] mb-4">
          Potency (vina_norm) vs ADMET Score · Pareto-optimal candidates highlighted
        </p>
        {hasRealData ? (
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 30, left: 10 }}>
              <CartesianGrid stroke="#3b494c" strokeOpacity={0.25} />
              <XAxis
                dataKey="admet" type="number" domain={[0, 1]} name="ADMET"
                tick={{ fill: '#bac9cc', fontSize: 11 }}
                label={{ value: 'ADMET Score', position: 'insideBottom', offset: -18, fill: '#849396', fontSize: 11 }}
              />
              <YAxis
                dataKey="potency" type="number" domain={[0, 1]} name="Potency"
                tick={{ fill: '#bac9cc', fontSize: 11 }}
                label={{ value: 'Potency (vina_norm)', angle: -90, position: 'insideLeft', fill: '#849396', fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{ background: '#1e2024', border: '1px solid #3b494c', borderRadius: 4, fontSize: 12, color: '#e2e2e8' }}
                formatter={(v, name) => [Number(v ?? 0).toFixed(3), name]}
                cursor={{ strokeDasharray: '3 3' }}
              />
              <ReferenceLine x={0.5} stroke="#9e9e9e" strokeDasharray="4" strokeOpacity={0.4} />
              <ReferenceLine y={0.5} stroke="#9e9e9e" strokeDasharray="4" strokeOpacity={0.4} />
              {/* Sub-optimal */}
              <Scatter
                data={scatterData.filter((d) => !d.pareto)}
                fill="#333539"
                stroke="#3b494c"
                strokeWidth={1}
                r={5}
              />
              {/* Pareto front */}
              <Scatter
                data={scatterData.filter((d) => d.pareto)}
                fill="#ffffff"
                stroke="#ffffff"
                strokeWidth={0}
                r={7}
              />
            </ScatterChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-64 flex items-center justify-center text-[var(--color-on-surface-variant)]">
            <div className="text-center space-y-2">
              <span className="material-symbols-outlined text-4xl text-[var(--color-outline)]">scatter_plot</span>
              <p className="text-sm">Run Phase 7 to populate the objective space.</p>
            </div>
          </div>
        )}
      </div>

      {/* Optimized Lead Candidates table */}
      <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-high)] flex items-center justify-between">
          <p className="font-semibold text-[var(--color-on-surface)]">Optimized Lead Candidates</p>
          <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">
            {paretoCount > 0 ? `${paretoCount} on Pareto front` : 'awaiting Phase 7 optimization'}
          </span>
        </div>

        {allLeads.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 gap-2 text-[var(--color-on-surface-variant)]">
            <span className="material-symbols-outlined text-4xl">analytics</span>
            <p className="text-sm">Phase 7 MPO hasn't produced candidates yet.</p>
            <p className="text-xs">Requires Phase 5/6 de novo generation to complete first.</p>
          </div>
        ) : (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-[var(--color-surface-container-highest)]/30">
                {['Candidate ID', 'SMILES', 'Pareto Rank', 'Desirability', 'Potency', 'ADMET', 'Novelty', ''].map((h) => (
                  <th key={h} className="px-4 py-3 text-[9px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-outline-variant)]">
              {allLeads.map((l) => (
                <tr key={l.id} className="hover:bg-[var(--color-surface-container-high)] transition-colors group">
                  <td className="px-4 py-3.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-[var(--color-primary-container)]">{l.id}</span>
                      {l.isPareto && (
                        <span className="text-[8px] px-1 py-0.5 bg-[var(--color-primary-container)]/15 border border-[var(--color-primary-container)]/30 rounded text-[var(--color-primary-container)] font-bold">
                          Pareto
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3.5 max-w-[180px]">
                    <span className="font-mono text-[10px] text-[var(--color-on-surface-variant)] bg-[var(--color-surface-container)] px-2 py-1 rounded border border-[var(--color-outline-variant)]/30 block truncate">
                      {l.smiles}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 font-mono text-xs text-[var(--color-on-surface)]">
                    {l.paretoRank != null ? `#${l.paretoRank}` : '—'}
                  </td>
                  <td className="px-4 py-3.5 font-mono text-xs text-[var(--color-secondary)]">
                    {l.desirability > 0 ? l.desirability.toFixed(3) : '—'}
                  </td>
                  <td className="px-4 py-3.5 font-mono text-xs text-[var(--color-primary-container)]">
                    {l.potency > 0 ? l.potency.toFixed(3) : '—'}
                  </td>
                  <td className="px-4 py-3.5 font-mono text-xs text-[var(--color-on-surface)]">
                    {l.admetScore > 0 ? l.admetScore.toFixed(3) : '—'}
                  </td>
                  <td className="px-4 py-3.5 font-mono text-xs text-[var(--color-on-surface)]">
                    {l.novelty > 0 ? l.novelty.toFixed(3) : '—'}
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    <button className="opacity-0 group-hover:opacity-100 bg-[var(--color-primary-container)] text-[var(--color-on-primary-container)] px-3 py-1 rounded text-[10px] font-bold transition-all">
                      Send to Synthesis
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

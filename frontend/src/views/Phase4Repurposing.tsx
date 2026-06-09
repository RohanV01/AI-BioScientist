import { useState } from 'react';
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer } from 'recharts';
import { useAppStore } from '../store';
import { useCandidates } from '../hooks/useRuns';
import type { ApiCandidate } from '../lib/api';

interface RepurposingDrug {
  name: string;
  target: string;
  overallScore: number;
  narrative: string;
  vinaScore: number | null;
  clinicalScore: number;
  lincsScore: number;
  kgScore: number;
  vinaNorm: number;
  mechanismOfAction: string;
  source: string;
  isCovalent: boolean;
  radar: { axis: string; value: number }[];
}

function candidateToRepurposing(c: ApiCandidate): RepurposingDrug {
  const sub = (c.subscores ?? {}) as Record<string, unknown>;
  const name = String(c.identifier ?? 'Unknown');
  const target = String(c.target_id ?? '—');
  const score = Number(c.combined_score ?? 0);
  const vinaScore = sub.vina_score != null ? Number(sub.vina_score) : null;
  const vinaNorm = Number(sub.vina_norm ?? 0);
  const clinicalScore = Number(sub.clinical_score ?? 0);
  const lincsScore = Number(sub.lincs_score ?? 0);
  const kgScore = Number(sub.kg_score ?? 0);
  return {
    name,
    target,
    overallScore: score,
    narrative: String(sub.narrative ?? `Repurposing score: ${score.toFixed(3)}`),
    vinaScore,
    clinicalScore,
    lincsScore,
    kgScore,
    vinaNorm,
    mechanismOfAction: String(sub.mechanism_of_action ?? sub.moa ?? ''),
    source: String(sub.source ?? ''),
    isCovalent: Boolean(sub.is_covalent_target ?? false),
    radar: [
      { axis: 'Docking',    value: Math.round(vinaNorm * 100) },
      { axis: 'Clinical',   value: Math.round(clinicalScore * 100) },
      { axis: 'Transcript', value: Math.round(lincsScore * 100) },
      { axis: 'KG',         value: Math.round(kgScore * 100) },
    ],
  };
}

export default function Phase4Repurposing() {
  const { activeRunId } = useAppStore();
  const { data: rawCandidates = [] } = useCandidates(activeRunId);
  const drugs: RepurposingDrug[] = rawCandidates
    .filter((c) => c.kind === 'repurposing')
    .map(candidateToRepurposing);
  const [selected, setSelected] = useState(0);
  const drug = drugs[Math.min(selected, drugs.length - 1)];

  if (!drug) return (
    <div className="flex flex-col items-center justify-center py-20 text-[var(--color-on-surface-variant)]">
      <span className="material-symbols-outlined text-4xl mb-2">medication</span>
      <p className="text-sm">No repurposing candidates yet — run Phase 4.</p>
    </div>
  );

  const clinicalPhase = drug.clinicalScore >= 0.9 ? 'Approved' :
    drug.clinicalScore >= 0.6 ? 'Phase 2/3' :
    drug.clinicalScore >= 0.3 ? 'Phase 1' : 'Preclinical';

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="border-b border-[var(--color-outline-variant)] pb-3">
        <h2 className="text-2xl font-bold text-[var(--color-on-surface)] mb-0.5">Phase 4: In-Silico Repurposing</h2>
        <p className="text-sm text-[var(--color-on-surface-variant)]">
          {drugs.length} candidate{drugs.length !== 1 ? 's' : ''} ranked by 4-signal triangulation: protein docking, transcriptomic reversal (LINCS), clinical precedent, and knowledge-graph edges.
        </p>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Left: drug cards */}
        <div className="col-span-4 space-y-3">
          {drugs.map((d, i) => (
            <button
              key={d.name}
              onClick={() => setSelected(i)}
              className={[
                'w-full text-left rounded-xl border transition-all overflow-hidden',
                i === selected
                  ? 'border-[var(--color-primary-container)] bg-[var(--color-surface-container-high)]'
                  : 'border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)] hover:bg-[var(--color-surface-container-high)]',
              ].join(' ')}
            >
              <div className="p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                      {/* Clinical stage badge */}
                      {d.clinicalScore >= 0.9 && (
                        <span className="text-[9px] font-bold uppercase tracking-widest border px-1.5 py-0.5 rounded bg-[var(--color-secondary)]/20 text-[var(--color-secondary)] border-[var(--color-secondary)]/40">
                          FDA APPROVED
                        </span>
                      )}
                      {d.clinicalScore >= 0.6 && d.clinicalScore < 0.9 && (
                        <span className="text-[9px] font-bold uppercase tracking-widest border px-1.5 py-0.5 rounded bg-[var(--color-primary-container)]/20 text-[var(--color-primary-container)] border-[var(--color-primary-container)]/40">
                          PHASE 2/3
                        </span>
                      )}
                      {/* Source badge */}
                      {d.source === 'chembl_mechanism' && (
                        <span className="text-[9px] font-bold uppercase tracking-widest border px-1.5 py-0.5 rounded bg-[var(--color-secondary)]/10 text-[var(--color-secondary)] border-[var(--color-secondary)]/20">
                          TIER 1
                        </span>
                      )}
                      {/* Covalent badge */}
                      {d.isCovalent && (
                        <span className="text-[9px] font-bold uppercase tracking-widest border px-1.5 py-0.5 rounded bg-[#fbbf24]/15 text-[#fbbf24] border-[#fbbf24]/30">
                          COVALENT
                        </span>
                      )}
                    </div>
                    <h3 className={`font-bold text-base ${i === selected ? 'text-[var(--color-primary-container)]' : 'text-[var(--color-on-surface)]'}`}>
                      {d.name}
                    </h3>
                    <p className="text-[11px] text-[var(--color-on-surface-variant)]">{d.target}</p>
                  </div>
                  <div className="text-right shrink-0 ml-2">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)]">Score</p>
                    <p className="font-mono text-2xl font-bold text-[var(--color-secondary)]">{(d.overallScore * 100).toFixed(1)}</p>
                  </div>
                </div>

                {/* Mechanism of action */}
                {d.mechanismOfAction && (
                  <p className="font-mono text-[10px] text-[var(--color-on-surface-variant)] bg-[var(--color-surface-container-lowest)] border border-[var(--color-outline-variant)]/40 rounded p-2 mb-2 truncate" title={d.mechanismOfAction}>
                    {d.mechanismOfAction}
                  </p>
                )}

                {/* Vina score + clinical stage */}
                <div className="flex items-center gap-3 text-[10px] text-[var(--color-on-surface-variant)]">
                  {d.vinaScore != null && (
                    <span>Vina <span className="font-mono text-[var(--color-secondary)] ml-1">{d.vinaScore.toFixed(1)} kcal/mol</span></span>
                  )}
                  <span className="font-semibold text-[var(--color-on-surface)]">{clinicalPhase}</span>
                </div>
              </div>

              {/* Score bar */}
              <div className="h-0.5 w-full bg-[var(--color-surface-container-highest)]">
                <div className="h-full bg-[var(--color-primary-container)]" style={{ width: `${d.overallScore * 100}%` }} />
              </div>
            </button>
          ))}
        </div>

        {/* Center: real 4-signal radar + narrative */}
        <div className="col-span-8 space-y-4">
          <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-5">
            <div className="flex items-center justify-between mb-1">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">4-Signal Triangulation</p>
                <h3 className="text-lg font-bold text-[var(--color-on-surface)]">{drug.name}</h3>
                <p className="text-xs text-[var(--color-on-surface-variant)]">Docking 35% · Clinical 30% · Transcriptomic 20% · KG 15%</p>
              </div>
              <div className="text-right">
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)]">Overall Score</p>
                <p className="font-mono text-3xl font-bold text-[var(--color-secondary)]">{(drug.overallScore * 100).toFixed(1)}</p>
              </div>
            </div>

            <ResponsiveContainer width="100%" height={260}>
              <RadarChart data={drug.radar} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
                <PolarGrid stroke="#3b494c" strokeOpacity={0.6} />
                <PolarAngleAxis
                  dataKey="axis"
                  tick={{ fill: '#bac9cc', fontSize: 11, fontFamily: 'Inter' }}
                />
                <Radar
                  dataKey="value"
                  stroke="#ffffff"
                  fill="#ffffff"
                  fillOpacity={0.15}
                  strokeWidth={2}
                />
              </RadarChart>
            </ResponsiveContainer>

            {/* Signal breakdown row */}
            <div className="flex gap-3 mt-2 text-[10px]">
              {[
                { label: 'Docking', value: drug.vinaNorm, raw: drug.vinaScore != null ? `${drug.vinaScore.toFixed(1)} kcal/mol` : null },
                { label: 'Clinical', value: drug.clinicalScore, raw: clinicalPhase },
                { label: 'LINCS', value: drug.lincsScore, raw: null },
                { label: 'KG', value: drug.kgScore, raw: null },
              ].map(({ label, value, raw }) => (
                <div key={label} className="flex-1 bg-[var(--color-surface-container)] border border-[var(--color-outline-variant)] rounded p-2 text-center">
                  <p className="font-bold uppercase tracking-wider text-[var(--color-outline)] mb-0.5">{label}</p>
                  <p className="font-mono font-semibold text-[var(--color-primary-container)]">{(value * 100).toFixed(0)}</p>
                  {raw && <p className="text-[var(--color-on-surface-variant)] mt-0.5 truncate">{raw}</p>}
                </div>
              ))}
            </div>
          </div>

          {/* LLM narrative */}
          <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-5 relative">
            <div className="absolute top-0 left-0 w-1 h-full bg-[var(--color-secondary)] rounded-l" />
            <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-2 flex items-center gap-1">
              <span className="material-symbols-outlined text-xs">auto_awesome</span> AI Narrative
            </p>
            <p className="text-sm text-[var(--color-on-surface)] leading-relaxed">{drug.narrative}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

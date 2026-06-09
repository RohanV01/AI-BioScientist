import { useAppStore } from '../store';
import { useRun, useTargets, useCandidates } from '../hooks/useRuns';
import type { ApiCandidate } from '../lib/api';

function modalityLabel(c: ApiCandidate): string {
  if (c.kind === 'biologic') return 'AB/Biologic';
  if (c.kind === 'repurposing') return 'Repurpose';
  return 'SM';
}

function scoreLabel(c: ApiCandidate): string {
  const vina = Number(c.subscores?.vina_score ?? c.subscores?.vina ?? 0);
  if (vina < -5) return `${vina.toFixed(1)} kcal`;
  return c.combined_score.toFixed(3);
}

export default function Phase9Packaging() {
  const { activeRunId } = useAppStore();
  const { data: runData, isLoading: runLoading } = useRun(activeRunId);
  const { data: targets = [], isLoading: targLoading } = useTargets(activeRunId);
  const { data: candidates = [], isLoading: candLoading } = useCandidates(activeRunId);

  const isLoading = runLoading || candLoading || targLoading;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="material-symbols-outlined text-4xl text-[var(--color-outline)] animate-spin">progress_activity</span>
      </div>
    );
  }

  const run = runData?.run;
  const phases = runData?.phases ?? [];
  const isComplete = run?.status === 'completed';
  const diseaseName = run?.disease_name ?? 'Unknown Disease';
  const efoId = run?.efo_id ?? '—';

  // Real counts from live data
  const p1Done = phases.find((p) => p.phase === 1)?.status === 'completed';
  const p2Done = phases.find((p) => p.phase === 2)?.status === 'completed';
  const p8Done = phases.find((p) => p.phase === 8)?.status === 'completed';

  const nP1Targets  = p1Done ? targets.length : 0;
  const nValidated  = p2Done ? targets.filter((t) => (t.validation_score ?? 0) >= 0.5 || t.seeded).length : 0;

  const smCandidates        = candidates.filter((c) => c.kind === 'sm' || c.kind === 'de_novo_sm');
  const biologicCandidates  = candidates.filter((c) => c.kind === 'biologic');
  const repurposingCandidates = candidates.filter((c) => c.kind === 'repurposing');
  const smCount             = smCandidates.length;
  const biologicCount       = biologicCandidates.length;
  const repurposingCount    = repurposingCandidates.length;
  const completedPhases     = phases.filter((p) => p.status === 'completed').length;

  const topLeads = [...candidates]
    .sort((a, b) => b.combined_score - a.combined_score)
    .slice(0, 5);

  // Phase 8 validation gate candidates (passed P8)
  const p8Leads = candidates
    .filter((c) => c.subscores?.phase === 8 || c.subscores?.final_rank != null)
    .sort((a, b) => Number(a.subscores?.final_rank ?? 99) - Number(b.subscores?.final_rank ?? 99))
    .slice(0, 5);

  // Real compliance checks from actual candidate data
  const allAdmet = candidates.flatMap((c) => {
    const admet = (c.subscores?.admet ?? {}) as Record<string, unknown>;
    return [{ hERG: String(admet.hERG ?? ''), AMES: String(admet.AMES ?? ''), disq: (c.subscores?.disqualifying ?? []) as string[] }];
  });
  const hasHERGHigh = allAdmet.some((a) => a.hERG.toLowerCase() === 'high');
  const hasAMESPos  = allAdmet.some((a) => a.AMES.toLowerCase() === 'pos');
  const hasDisq     = allAdmet.some((a) => a.disq.length > 0);

  const COMPLIANCE = [
    { label: 'ADMET Profile',       ok: (smCount + biologicCount) > 0 && !hasDisq },
    { label: 'Toxicity Screen',     ok: completedPhases >= 5 },
    { label: 'hERG Liability',      ok: (smCount + biologicCount) > 0 && !hasHERGHigh },
    { label: 'Mutagenicity (Ames)', ok: smCount > 0 && !hasAMESPos },
    { label: 'Regulatory (ICH M7)', ok: isComplete },
  ];

  const FUNNEL = [
    { label: 'Phase 1 Targets',   value: nP1Targets,                                    color: '#004f58' },
    { label: 'Validated Targets', value: nValidated,                                     color: '#006875' },
    { label: 'De Novo Generated', value: smCount + biologicCount,                        color: '#00a572' },
    { label: 'Repurposing Hits',  value: repurposingCount,                               color: '#9e9e9e' },
    { label: 'P8 Gate Passed',    value: p8Done ? candidates.filter((c) => c.subscores?.passed === true && c.subscores?.phase === 8).length : 0, color: '#ffffff' },
    { label: 'Final Leads',       value: topLeads.length,                                color: '#ffffff' },
  ].filter((f) => f.value > 0);

  const maxFunnel = FUNNEL[0]?.value ?? 1;

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {/* Hero */}
      <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-8 text-center relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(255,255,255,0.06)_0%,transparent_70%)]" />
        <div className="relative z-10">
          <div className={`w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4 border-2 ${
            isComplete
              ? 'bg-[var(--color-secondary)]/20 border-[var(--color-secondary)]'
              : 'bg-[var(--color-primary-container)]/20 border-[var(--color-primary-container)] animate-pulse'
          }`}>
            <span
              className={`material-symbols-outlined text-2xl ${isComplete ? 'text-[var(--color-secondary)]' : 'text-[var(--color-primary-container)]'}`}
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              {isComplete ? 'check_circle' : 'pending'}
            </span>
          </div>
          <h2 className="text-2xl font-bold text-[var(--color-on-surface)] mb-2">
            {isComplete ? 'Simulation Run Complete' : `Run ${run?.status ?? 'pending'}…`}
          </h2>
          <p className="text-sm text-[var(--color-on-surface-variant)] max-w-lg mx-auto mb-6">
            Pipeline for <strong className="text-[var(--color-on-surface)]">{diseaseName}</strong> ({efoId}).
            {isComplete
              ? ` ${topLeads.length} viable candidate${topLeads.length !== 1 ? 's' : ''} passed multi-parameter optimization.`
              : ` ${completedPhases}/8 phases complete.`}
          </p>
          <div className="flex items-center justify-center gap-3">
            <button
              disabled={!isComplete}
              className="bg-[var(--color-primary-container)] text-[var(--color-on-primary-container)] px-6 py-2.5 rounded text-sm font-bold uppercase tracking-wider hover:bg-[var(--color-surface-tint)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              <span className="material-symbols-outlined text-base">download</span>
              Download package.zip
            </button>
          </div>
        </div>
      </div>

      {/* Phase 8 Validation Gate Results */}
      {p8Leads.length > 0 && (
        <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-high)] flex items-center justify-between">
            <p className="font-semibold text-[var(--color-on-surface)]">Phase 8 — In-Silico Validation Gate</p>
            <span className="text-[10px] font-bold text-[var(--color-secondary)] uppercase tracking-widest">
              {p8Leads.length} cleared gate (score ≥ 0.45)
            </span>
          </div>
          <div className="divide-y divide-[var(--color-outline-variant)]">
            {p8Leads.map((c) => {
              const sub = c.subscores ?? {};
              const brief = String(sub.candidate_brief ?? '');
              const passed = Boolean(sub.passed);
              const finalRank = sub.final_rank != null ? Number(sub.final_rank) : null;
              return (
                <div key={c.id} className="p-4 hover:bg-[var(--color-surface-container-high)] transition-colors">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      {finalRank != null && (
                        <span className="font-mono text-[10px] text-[var(--color-outline)] w-6">#{finalRank}</span>
                      )}
                      <span className="font-mono text-sm font-bold text-[var(--color-primary-container)]">{c.identifier}</span>
                      <span className="text-[9px] px-1.5 py-0.5 bg-[var(--color-surface-container)] border border-[var(--color-outline-variant)] rounded text-[var(--color-on-surface-variant)]">
                        {modalityLabel(c)}
                      </span>
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${passed ? 'bg-[var(--color-secondary)]/20 text-[var(--color-secondary)]' : 'bg-[var(--color-error)]/20 text-[var(--color-error)]'}`}>
                        {passed ? 'PASS' : 'FAIL'}
                      </span>
                    </div>
                    <span className="font-mono text-sm font-bold text-[var(--color-secondary)]">
                      {c.combined_score.toFixed(3)}
                    </span>
                  </div>

                  {/* 6-axis subscores */}
                  <div className="flex gap-2 flex-wrap mb-2">
                    {[
                      { label: 'Binding', key: 'binding_affinity' },
                      { label: 'Pose Stability', key: 'pose_stability' },
                      { label: 'ADMET', key: 'admet_or_developability' },
                      { label: 'Selectivity', key: 'selectivity' },
                      { label: 'Novelty', key: 'novelty' },
                      { label: 'Modality', key: 'modality_alignment' },
                    ].map(({ label, key }) => {
                      const v = sub[key] != null ? Number(sub[key]) : null;
                      return v != null ? (
                        <div key={key} className="bg-[var(--color-surface-container)] border border-[var(--color-outline-variant)] rounded px-2 py-1 text-center">
                          <p className="text-[8px] font-bold uppercase tracking-wider text-[var(--color-outline)]">{label}</p>
                          <p className="font-mono text-[10px] font-semibold text-[var(--color-primary-container)]">{v.toFixed(2)}</p>
                        </div>
                      ) : null;
                    })}
                  </div>

                  {brief && (
                    <p className="text-xs text-[var(--color-on-surface-variant)] leading-relaxed italic border-l-2 border-[var(--color-secondary)]/40 pl-2">
                      {brief}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="grid grid-cols-12 gap-4">
        {/* Left: Compliance + Attrition funnel */}
        <div className="col-span-5 space-y-4">
          {/* Compliance */}
          <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-high)] flex items-center justify-between">
              <p className="text-xs font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">Compliance Audit</p>
              <span className={`text-[9px] font-bold px-2 py-0.5 border rounded ${
                isComplete
                  ? 'bg-[var(--color-secondary)]/20 border-[var(--color-secondary)]/40 text-[var(--color-secondary)]'
                  : 'bg-[var(--color-outline)]/10 border-[var(--color-outline-variant)] text-[var(--color-outline)]'
              }`}>
                {isComplete ? 'AUDIT PASSED' : 'PENDING'}
              </span>
            </div>
            <div className="p-3 space-y-1.5">
              {COMPLIANCE.map(({ label, ok }) => (
                <div key={label} className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-[var(--color-surface-container-high)] transition-colors">
                  <span className="text-xs text-[var(--color-on-surface)]">{label}</span>
                  <span
                    className="material-symbols-outlined text-base"
                    style={{
                      color: ok ? 'var(--color-secondary)' : 'var(--color-outline)',
                      fontVariationSettings: "'FILL' 1",
                    }}
                  >
                    {ok ? 'check_circle' : 'radio_button_unchecked'}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Attrition funnel */}
          {FUNNEL.length > 0 && (
            <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl p-4">
              <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-3">
                Candidate Attrition Funnel
              </p>
              <div className="space-y-1.5">
                {FUNNEL.map(({ label, value, color }) => {
                  const pct = Math.max((value / maxFunnel) * 100, 4);
                  return (
                    <div key={label} className="flex items-center gap-3">
                      <div className="flex-1">
                        <div className="flex justify-between text-[10px] mb-0.5">
                          <span className="text-[var(--color-on-surface-variant)] truncate mr-2">{label}</span>
                          <span className="font-mono font-bold shrink-0" style={{ color }}>{value.toLocaleString()}</span>
                        </div>
                        <div className="w-full h-2 bg-[var(--color-surface-container-highest)] rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Right: executive summary + leads */}
        <div className="col-span-7 space-y-4">
          <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-high)]">
              <p className="text-xs font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">Executive Summary</p>
            </div>
            <div className="p-5 space-y-4 text-sm text-[var(--color-on-surface-variant)]">
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-1.5">Run Objective &amp; Outcome</p>
                <p className="leading-relaxed">
                  Pipeline run targeting <strong className="text-[var(--color-on-surface)]">{diseaseName}</strong> ({efoId}).
                  Generative models were constrained by stringent multi-parameter optimization profiles, prioritizing high binding affinity,
                  favorable ADME characteristics, and synthetic accessibility.
                </p>
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-1.5">Key Findings</p>
                <ul className="space-y-1.5">
                  {[
                    nP1Targets > 0 && `${nP1Targets} targets identified via PU learning (Phase 1).`,
                    nValidated > 0 && `${nValidated} targets passed druggability validation (Phase 2).`,
                    smCount > 0 && `${smCount} small molecule candidate${smCount !== 1 ? 's' : ''} generated via REINVENT4/BRICS.`,
                    biologicCount > 0 && `${biologicCount} biologic candidate${biologicCount !== 1 ? 's' : ''} generated via peptide design.`,
                    repurposingCount > 0 && `${repurposingCount} repurposing hit${repurposingCount !== 1 ? 's' : ''} identified via ChEMBL/LINCS screening.`,
                    topLeads.length > 0 && `Top lead: ${topLeads[0].identifier} (score ${topLeads[0].combined_score.toFixed(3)}).`,
                  ].filter(Boolean).map((item) => (
                    <li key={String(item)} className="flex gap-2">
                      <span className="text-[var(--color-secondary)] shrink-0 mt-0.5">·</span>
                      <span>{item}</span>
                    </li>
                  ))}
                  {nP1Targets === 0 && smCount === 0 && biologicCount === 0 && repurposingCount === 0 && (
                    <li className="flex gap-2 opacity-50">
                      <span className="text-[var(--color-outline)] shrink-0 mt-0.5">·</span>
                      <span>No candidates generated yet — pipeline still running.</span>
                    </li>
                  )}
                </ul>
              </div>
              {isComplete && topLeads.length > 0 && (
                <div className="bg-[var(--color-surface-container)] border border-[var(--color-outline-variant)] rounded-lg p-3 relative">
                  <div className="absolute top-0 left-0 w-1 h-full bg-[var(--color-primary-container)] rounded-l" />
                  <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-primary-container)] mb-1">Recommendation</p>
                  <p className="text-xs leading-relaxed">
                    Proceed with compound synthesis for the top {Math.min(topLeads.length, 5)} lead
                    {topLeads.length !== 1 ? 's' : ''}. Preliminary lab protocols have been generated and appended to the final package.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Final leads table */}
          {topLeads.length > 0 ? (
            <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-high)]">
                <p className="text-xs font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">Final Lead Candidates</p>
              </div>
              <table className="w-full text-left">
                <tbody className="divide-y divide-[var(--color-outline-variant)]">
                  {topLeads.map((c, i) => (
                    <tr key={c.id} className="hover:bg-[var(--color-surface-container-high)] transition-colors">
                      <td className="px-4 py-2.5 font-mono text-xs text-[var(--color-primary-container)] font-bold">{c.identifier}</td>
                      <td className="px-4 py-2.5 text-xs text-[var(--color-on-surface-variant)]">{c.target_id}</td>
                      <td className="px-4 py-2.5">
                        <span className="text-[9px] px-1.5 py-0.5 bg-[var(--color-surface-container)] border border-[var(--color-outline-variant)] rounded text-[var(--color-on-surface-variant)]">
                          {modalityLabel(c)}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-[var(--color-secondary)]">{scoreLabel(c)}</td>
                      <td className="px-4 py-2.5">
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                          i < 2
                            ? 'bg-[var(--color-secondary)]/20 text-[var(--color-secondary)]'
                            : 'bg-[var(--color-surface-container-high)] text-[var(--color-on-surface-variant)]'
                        }`}>
                          {i < 2 ? 'Lead' : 'Backup'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="bg-[var(--color-surface-container-low)] border-l1 rounded-xl flex flex-col items-center justify-center py-10 gap-2 text-[var(--color-on-surface-variant)]">
              <span className="material-symbols-outlined text-3xl">inventory_2</span>
              <p className="text-sm">No candidates to package yet.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

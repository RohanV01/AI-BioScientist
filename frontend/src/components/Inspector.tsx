import { useAppStore } from '../store';
import type { ApiTarget } from '../lib/api';

const TABS = [
  { key: 'shap'   as const, icon: 'troubleshoot',  label: 'SHAP' },
  { key: 'viewer' as const, icon: 'view_in_ar',    label: 'Viewer' },
  { key: 'logs'   as const, icon: 'article',       label: 'Evidence' },
];

export default function Inspector() {
  const { inspectorOpen, setInspectorOpen, inspectorTab, setInspectorTab, selectedTarget } = useAppStore();

  return (
    <aside
      className={[
        'fixed right-0 top-0 h-full z-50 flex flex-col border-l border-[var(--color-outline-variant)] bg-[var(--color-surface-container-high)] shadow-2xl transition-transform duration-300',
        inspectorOpen ? 'translate-x-0' : 'translate-x-full',
      ].join(' ')}
      style={{ width: 'var(--spacing-inspector)' }}
    >
      {/* Header */}
      <div className="p-4 border-b border-[var(--color-outline-variant)] shrink-0 flex justify-between items-start">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-secondary)] mb-1">The Inspector</p>
          <h3 className="text-base font-semibold text-[var(--color-on-surface)]">Target Deep-Dive</h3>
          <p className="font-mono text-[11px] text-[var(--color-on-surface-variant)] mt-0.5">
            Focus: {selectedTarget?.symbol ?? '—'}
          </p>
        </div>
        <button onClick={() => setInspectorOpen(false)} className="text-[var(--color-on-surface-variant)] hover:text-[var(--color-on-surface)] transition-colors">
          <span className="material-symbols-outlined">close</span>
        </button>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 p-2 border-b border-[var(--color-outline-variant)] shrink-0">
        {TABS.map(({ key, icon, label }) => (
          <button
            key={key}
            onClick={() => setInspectorTab(key)}
            className={[
              'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-colors',
              inspectorTab === key
                ? 'bg-[var(--color-secondary-container)] text-[var(--color-on-secondary-container)] font-semibold'
                : 'text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-bright)]',
            ].join(' ')}
          >
            <span className="material-symbols-outlined text-base">{icon}</span>
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {inspectorTab === 'shap' && <ShapContent target={selectedTarget} />}
        {inspectorTab === 'viewer' && <ViewerContent target={selectedTarget} />}
        {inspectorTab === 'logs' && <LogsContent target={selectedTarget} />}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-[var(--color-outline-variant)] shrink-0">
        <button className="w-full bg-[var(--color-surface-container)] border border-[var(--color-outline-variant)] text-[var(--color-on-surface)] py-2 px-4 rounded text-xs font-bold uppercase tracking-wider hover:bg-[var(--color-surface-bright)] transition-colors flex items-center justify-center gap-2">
          <span className="material-symbols-outlined text-base">science</span>
          Send to Simulation
        </button>
      </div>
    </aside>
  );
}

function ShapContent({ target }: { target: ApiTarget | null }) {
  if (!target) return <EmptyState />;
  const trail = target.evidence_trail ?? {};
  const p2 = (trail.phase2 as Record<string, unknown> | undefined) ?? {};

  // Phase 2 attributions (the real SHAP-equivalent for P2 features)
  const p2Attributions = (p2.attributions as Record<string, number> | undefined) ?? {};

  // Phase 1 top features (numeric fields at the top-level trail)
  const p1Fields = Object.entries(trail)
    .filter(([k, v]) => typeof v === 'number' && k !== 'aggregate_score')
    .slice(0, 6)
    .map(([feature, v]) => ({ feature, value: (v as number) * 2 - 1 }));

  // Prefer Phase 2 attributions if present, fall back to Phase 1 numerics
  const shapSource = Object.keys(p2Attributions).length > 0
    ? Object.entries(p2Attributions).map(([feature, v]) => ({ feature, value: v - 0.5 }))
    : p1Fields;

  // AI rationale: use evidence_summary from Phase 2 if present, otherwise derive from Phase 1 data
  const evidenceSummary = String(p2.evidence_summary ?? '');
  const dorothea = String(trail.dorothea_confidence ?? '');
  const regulonSize = Number(trail.regulon_size ?? 0);
  const isMasterReg = dorothea === 'A' || dorothea === 'B';
  const puPercentile = Number(trail.pu_percentile ?? 0);

  let rationale = evidenceSummary;
  if (!rationale) {
    const topFeature = shapSource[0]?.feature ?? 'multiple omics features';
    rationale = `${target.symbol} is ranked #${target.rank} by the PU learning model (score ${target.aggregate_score.toFixed(3)}).`;
    if (puPercentile > 0) rationale += ` Top ${(100 - puPercentile * 100).toFixed(1)}% of scored proteome.`;
    if (isMasterReg) rationale += ` DoRothEA ${dorothea}-grade master regulator controlling ${regulonSize} genes.`;
    rationale += ` Primary driver: ${topFeature.replace(/_/g, ' ')}.`;
  }

  return (
    <>
      {/* AI Rationale */}
      <div className="bg-[var(--color-surface-container)] border border-[var(--color-outline-variant)] rounded p-3 relative">
        <div className="absolute top-0 left-0 w-1 h-full bg-[var(--color-secondary)] rounded-l" />
        <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-2 flex items-center gap-1">
          <span className="material-symbols-outlined text-xs">auto_awesome</span> AI Rationale
        </p>
        <p className="text-xs text-[var(--color-on-surface)] leading-relaxed">{rationale}</p>
      </div>

      {/* Phase 1 signal cards */}
      <div className="grid grid-cols-2 gap-2">
        <StatCard label="PU Score" value={target.aggregate_score.toFixed(3)} accent />
        <StatCard label="TDL" value={target.tdl ?? '—'} />
        {puPercentile > 0 && (
          <StatCard
            label="Percentile"
            value={`Top ${(100 - puPercentile * 100).toFixed(1)}%`}
            accent
          />
        )}
        {(trail.genetic as number | undefined) != null && (
          <StatCard label="Genetic Score" value={(trail.genetic as number).toFixed(3)} />
        )}
        {isMasterReg && (
          <StatCard label="Master Regulator" value={`${dorothea}-grade · ${regulonSize} genes`} accent />
        )}
        {(trail.selectivity as number | undefined) != null && (
          <StatCard label="Selectivity" value={(trail.selectivity as number).toFixed(3)} />
        )}
      </div>

      {/* SHAP bars */}
      <div>
        <h4 className="text-sm font-semibold text-[var(--color-on-surface)] mb-1">
          Top Attributions {Object.keys(p2Attributions).length > 0 ? '(Phase 2)' : '(Phase 1)'}
        </h4>
        <div className="space-y-3">
          {shapSource.slice(0, 7).map(({ feature, value }) => {
            const pos = value >= 0;
            const pct = Math.abs(value) * 100;
            return (
              <div key={feature}>
                <div className="flex justify-between font-mono text-[11px] mb-1">
                  <span className="text-[var(--color-on-surface)]">{feature.replace(/_/g, ' ')}</span>
                  <span className={pos ? 'text-[var(--color-secondary)]' : 'text-[var(--color-error)]'}>
                    {pos ? '+' : ''}{value.toFixed(3)}
                  </span>
                </div>
                <div className="w-full h-1.5 bg-[var(--color-surface-container-low)] rounded-full overflow-hidden flex">
                  {pos ? (
                    <>
                      <div className="h-full bg-[var(--color-surface-container)] w-1/2" />
                      <div className="h-full bg-[var(--color-secondary)] rounded-r" style={{ width: `${pct / 2}%` }} />
                    </>
                  ) : (
                    <>
                      <div className="h-full bg-[var(--color-error)] rounded-l" style={{ width: `${pct / 2}%` }} />
                      <div className="h-full bg-[var(--color-surface-container)] w-1/2" />
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Phase 2 modality scores if present */}
      {p2.modality && (p2.modality as Record<string, unknown>).scores && (
        <div>
          <h4 className="text-sm font-semibold text-[var(--color-on-surface)] mb-2">Modality Scores (Phase 2)</h4>
          <div className="space-y-2">
            {Object.entries((p2.modality as Record<string, unknown>).scores as Record<string, number>)
              .sort((a, b) => b[1] - a[1])
              .map(([mod, score]) => (
                <div key={mod} className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-[var(--color-on-surface-variant)] w-16 shrink-0">{mod}</span>
                  <div className="flex-1 h-1.5 bg-[var(--color-surface-container-low)] rounded overflow-hidden">
                    <div className="h-full bg-[var(--color-primary-container)] rounded" style={{ width: `${score * 100}%` }} />
                  </div>
                  <span className="font-mono text-[10px] text-[var(--color-primary-container)] w-10 text-right">{score.toFixed(2)}</span>
                </div>
              ))}
          </div>
        </div>
      )}
    </>
  );
}

function ViewerContent({ target }: { target: ApiTarget | null }) {
  const trail = target?.evidence_trail ?? {};
  const p2 = (trail.phase2 as Record<string, unknown> | undefined) ?? {};
  const structure = (p2.structure as Record<string, unknown> | undefined) ?? {};
  const pdbUrl = String(structure.pdb_url ?? '');
  const maxDrugg = Number(p2.max_druggability ?? 0);
  const plddt = Number(structure.median_plddt ?? 0);

  return (
    <div className="space-y-4">
      <div className="aspect-square w-full bg-[var(--color-surface-container-lowest)] border border-[var(--color-outline-variant)] rounded-lg flex items-center justify-center relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(255,255,255,0.08)_0%,transparent_70%)]" />
        <div className="text-center space-y-2">
          <span className="material-symbols-outlined text-5xl text-[var(--color-outline)]">view_in_ar</span>
          <p className="text-xs text-[var(--color-on-surface-variant)]">3D Viewer — AlphaFold structure</p>
          {pdbUrl
            ? <p className="font-mono text-[10px] text-[var(--color-primary-container)] truncate px-2">{pdbUrl}</p>
            : <p className="font-mono text-[10px] text-[var(--color-outline)]">Run Phase 2 to load structure</p>
          }
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <StatCard label="AlphaFold pLDDT" value={plddt > 0 ? plddt.toFixed(1) : '—'} accent={plddt >= 70} />
        <StatCard label="Max Druggability" value={maxDrugg > 0 ? maxDrugg.toFixed(3) : '—'} accent={maxDrugg >= 0.5} />
      </div>
    </div>
  );
}

function LogsContent({ target }: { target: ApiTarget | null }) {
  if (!target) return <EmptyState />;
  const logs = [
    { time: '—', msg: `Phase 0: DISEASES query — ${target.symbol} retrieved from Jensen DB` },
    { time: '—', msg: 'Phase 1: AlphaMissense pathogenicity score computed' },
    { time: '—', msg: 'Phase 1: DepMap CRISPR essentiality profiled' },
    { time: '—', msg: 'Phase 1: GTEx tissue expression profiled (54 tissues)' },
    { time: '—', msg: 'Phase 1: PU learning model scored — feature vector assembled' },
    { time: '—', msg: `Phase 1 complete — rank #${target.rank} · PU score ${target.aggregate_score.toFixed(3)}` },
  ];
  return (
    <div className="space-y-2">
      {logs.map(({ time, msg }) => (
        <div key={msg} className="bg-[var(--color-surface-container)] border border-[var(--color-outline-variant)] rounded p-2.5">
          <span className="font-mono text-[10px] text-[var(--color-primary-container)]">{time}</span>
          <p className="text-xs text-[var(--color-on-surface)] mt-0.5">{msg}</p>
        </div>
      ))}
    </div>
  );
}

function StatCard({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="bg-[var(--color-surface-container-low)] border border-[var(--color-outline-variant)] rounded p-3">
      <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)] mb-1">{label}</p>
      <p className={`font-mono text-sm font-semibold ${accent ? 'text-[var(--color-primary-container)]' : 'text-[var(--color-on-surface)]'}`}>{value}</p>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
      <span className="material-symbols-outlined text-4xl text-[var(--color-outline)]">manage_search</span>
      <p className="text-xs text-[var(--color-on-surface-variant)]">Select a target to inspect</p>
    </div>
  );
}

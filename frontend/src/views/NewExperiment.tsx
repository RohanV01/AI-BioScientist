import { useState, useEffect, useRef } from 'react';
import { useAppStore } from '../store';
import { useCreateRun } from '../hooks/useRuns';
import { api } from '../lib/api';

const MODES = [
  {
    value:  'explore'  as const,
    icon:   'biotech',
    label:  'Explore',
    sub:    'Novel targets',
    desc:   'Discover druggable targets using PU learning and multi-omics scoring.',
  },
  {
    value:  'repurpose' as const,
    icon:   'rebase_edit',
    label:  'Repurpose',
    sub:    'Known drugs',
    desc:   'Screen approved compounds for activity on your disease targets.',
  },
  {
    value:  'de_novo'  as const,
    icon:   'medication',
    label:  'De Novo',
    sub:    'Generative',
    desc:   'Generate novel small molecules and biologics from scratch.',
  },
];

const PHASES = [
  { id: 1, label: 'Target ID'  },
  { id: 2, label: 'Validation' },
  { id: 3, label: 'Routing'    },
  { id: 4, label: 'Repurpose'  },
  { id: 5, label: 'De Novo SM' },
  { id: 6, label: 'Biologics'  },
  { id: 7, label: 'MPO'        },
  { id: 8, label: 'Packaging'  },
];

const STEPS = ['Mode', 'Context', 'Targets'] as const;

const inputCls = [
  'w-full bg-[var(--color-surface-container)] border border-[var(--color-outline-variant)] rounded',
  'px-3 py-2.5 text-sm text-[var(--color-on-surface)]',
  'placeholder:text-[var(--color-on-surface-variant)]/50',
  'focus:outline-none focus:border-[var(--color-outline)] focus:ring-1 focus:ring-white/5',
  'transition-colors',
].join(' ');

function SectionLabel({ children }: { children: string }) {
  return (
    <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-3">
      {children}
    </p>
  );
}

function FieldLabel({ children, required, hint }: { children: string; required?: boolean; hint?: string }) {
  return (
    <label className="flex items-baseline gap-1.5 text-xs text-[var(--color-on-surface-variant)] mb-1.5">
      {children}
      {required && <span className="text-[var(--color-primary-container)] text-[10px]">required</span>}
      {hint && <span className="text-[10px] text-[var(--color-on-surface-variant)]/50">{hint}</span>}
    </label>
  );
}

export default function NewExperiment() {
  const { setActiveRunId, setHomeTab } = useAppStore();
  const createRun = useCreateRun();

  const [disease, setDisease]           = useState('');
  const [efoId, setEfoId]               = useState('');
  const [geneQuery, setGeneQuery]       = useState('');
  const [suggestions, setSuggestions]   = useState<string[]>([]);
  const [seedGenes, setSeedGenes]       = useState<string[]>([]);
  const [seedSmilesText, setSeedSmilesText] = useState('');
  const [throughPhase, setThroughPhase] = useState(8);
  const [tissue, setTissue]             = useState('');
  const [intentMode, setIntentMode]     = useState<'explore' | 'repurpose' | 'de_novo'>('explore');
  const [showAdv, setShowAdv]           = useState(false);
  const [error, setError]               = useState<string | null>(null);
  const suggestRef = useRef<HTMLDivElement>(null);
  const inputRef   = useRef<HTMLInputElement>(null);

  // Breadcrumb step completion
  const stepDone = [
    true,
    !!(disease.trim() && efoId.trim()),
    seedGenes.length > 0,
  ];
  const currentStep = stepDone[2] ? 2 : stepDone[1] ? 1 : 0;

  // Gene autocomplete
  useEffect(() => {
    if (geneQuery.length < 2) { setSuggestions([]); return; }
    const t = setTimeout(async () => {
      try {
        const res = await api.genes(geneQuery, 8);
        setSuggestions(res.results);
      } catch {
        setSuggestions([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [geneQuery]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        suggestRef.current && !suggestRef.current.contains(e.target as Node) &&
        inputRef.current   && !inputRef.current.contains(e.target as Node)
      ) setSuggestions([]);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const addGene = (g: string) => {
    const upper = g.trim().toUpperCase();
    if (upper && !seedGenes.includes(upper)) setSeedGenes((prev) => [...prev, upper]);
    setGeneQuery('');
    setSuggestions([]);
    inputRef.current?.focus();
  };

  const addGenes = (raw: string) => {
    const tokens = raw.split(/[\s,;]+/).map((t) => t.trim().toUpperCase()).filter(Boolean);
    if (!tokens.length) return;
    setSeedGenes((prev) => {
      const set = new Set(prev);
      tokens.forEach((t) => set.add(t));
      return [...set];
    });
    setGeneQuery('');
    setSuggestions([]);
    inputRef.current?.focus();
  };

  const removeGene = (g: string) => setSeedGenes((prev) => prev.filter((x) => x !== g));

  const parsedSeedSmiles = seedSmilesText
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 4);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const result = await createRun.mutateAsync({
        disease,
        disease_efo_id: efoId,
        known_positives: seedGenes,
        seed_smiles: parsedSeedSmiles,
        intent_mode: intentMode,
        tissue_of_interest: tissue || undefined,
        through_phase: throughPhase,
      });
      setActiveRunId(result.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create experiment');
    }
  };

  const canSubmit = !!(disease.trim() && efoId.trim() && seedGenes.length > 0 && !createRun.isPending);
  const selectedMode = MODES.find((m) => m.value === intentMode)!;

  return (
    <div className="h-full flex flex-col bg-[var(--color-background)] text-[var(--color-on-surface)]">

      {/* ── Top bar ──────────────────────────────────────────────────── */}
      <div className="shrink-0 flex items-center justify-between px-8 h-14 border-b border-[var(--color-outline-variant)]">
        <button
          onClick={() => setHomeTab('dashboard')}
          className="flex items-center gap-1 text-[11px] text-[var(--color-on-surface-variant)] hover:text-[var(--color-on-surface)] transition-colors"
        >
          <span className="material-symbols-outlined text-[14px]">arrow_back</span>
          Overview
        </button>

        {/* 3-step breadcrumb */}
        <div className="flex items-center gap-1">
          {STEPS.map((step, idx) => (
            <div key={step} className="flex items-center gap-1">
              <div className={[
                'flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium transition-colors',
                idx < currentStep
                  ? 'text-[var(--color-on-surface-variant)]'
                  : idx === currentStep
                  ? 'text-[var(--color-on-surface)] bg-[var(--color-surface-container-high)]'
                  : 'text-[var(--color-on-surface-variant)]/30',
              ].join(' ')}>
                {stepDone[idx] && idx < currentStep && (
                  <span className="material-symbols-outlined text-[11px]" style={{ fontVariationSettings: "'FILL' 1" }}>
                    check
                  </span>
                )}
                {step}
              </div>
              {idx < STEPS.length - 1 && (
                <span className="material-symbols-outlined text-[12px] text-[var(--color-on-surface-variant)]/25">
                  chevron_right
                </span>
              )}
            </div>
          ))}
        </div>

        <span className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)]">
          New Experiment
        </span>
      </div>

      {/* ── Two-column form ──────────────────────────────────────────── */}
      <form id="new-exp-form" onSubmit={handleSubmit} className="flex flex-1 min-h-0 overflow-hidden">

        {/* LEFT: Mode + Depth + Advanced (40%) */}
        <div className="w-[40%] border-r border-[var(--color-outline-variant)] flex flex-col overflow-y-auto">
          <div className="px-6 pt-6 space-y-6 pb-6">

            {/* Pipeline Mode — vertical selector */}
            <div>
              <SectionLabel>Pipeline Mode</SectionLabel>
              <div className="space-y-1.5">
                {MODES.map((m) => {
                  const active = m.value === intentMode;
                  return (
                    <button
                      key={m.value}
                      type="button"
                      onClick={() => setIntentMode(m.value)}
                      className={[
                        'w-full text-left flex items-start gap-3 px-3 py-3 rounded border transition-all',
                        active
                          ? 'bg-[var(--color-surface-container-high)] border-[var(--color-outline)] border-l-2 border-l-[var(--color-primary-container)]'
                          : 'bg-[var(--color-surface-container)] border-[var(--color-outline-variant)] hover:bg-[var(--color-surface-container-high)]',
                      ].join(' ')}
                    >
                      <span
                        className="material-symbols-outlined text-[16px] mt-0.5 shrink-0 transition-colors"
                        style={{
                          color: active ? 'var(--color-primary-container)' : 'var(--color-on-surface-variant)',
                          fontVariationSettings: active ? "'FILL' 1" : undefined,
                        }}
                      >
                        {m.icon}
                      </span>
                      <div>
                        <p className={`text-[12px] font-semibold transition-colors ${active ? 'text-[var(--color-on-surface)]' : 'text-[var(--color-on-surface-variant)]'}`}>
                          {m.label}
                          <span className="ml-1.5 text-[10px] font-normal opacity-50">{m.sub}</span>
                        </p>
                        <p className="text-[10px] text-[var(--color-on-surface-variant)]/60 mt-0.5 leading-snug">
                          {m.desc}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Pipeline Depth */}
            <div>
              <SectionLabel>Pipeline Depth</SectionLabel>
              <p className="text-[10px] text-[var(--color-on-surface-variant)]/70 mb-3 -mt-1">
                Terminal phase: P{throughPhase} · {(PHASES.find((p) => p.id === throughPhase) ?? PHASES[PHASES.length - 1]).label}
              </p>
              <div className="flex gap-1">
                {PHASES.map(({ id, label }) => {
                  const active     = id <= throughPhase;
                  const isTerminal = id === throughPhase;
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setThroughPhase(id)}
                      title={`P${id} · ${label}`}
                      className={[
                        'flex-1 py-2 rounded text-[10px] font-bold transition-all',
                        isTerminal
                          ? 'bg-[var(--color-primary-container)] text-[var(--color-on-primary)]'
                          : active
                          ? 'bg-[var(--color-surface-container-high)] text-[var(--color-on-surface)] border border-[var(--color-outline-variant)]'
                          : 'bg-[var(--color-surface-container)] text-[var(--color-on-surface-variant)]/35 border border-[var(--color-outline-variant)]',
                      ].join(' ')}
                    >
                      P{id}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Advanced */}
            <div className="border border-[var(--color-outline-variant)] rounded overflow-hidden">
              <button
                type="button"
                onClick={() => setShowAdv((v) => !v)}
                className="w-full flex items-center justify-between px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-container-high)] transition-colors"
              >
                <span className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[14px]">tune</span>
                  Advanced
                </span>
                <span className="material-symbols-outlined text-[14px]">
                  {showAdv ? 'expand_less' : 'expand_more'}
                </span>
              </button>
              {showAdv && (
                <div className="px-4 pb-4 pt-3 border-t border-[var(--color-outline-variant)] bg-[var(--color-surface-container)]">
                  <FieldLabel hint="Filters GTEx expression data">Tissue of Interest</FieldLabel>
                  <input
                    type="text"
                    value={tissue}
                    onChange={(e) => setTissue(e.target.value)}
                    placeholder="e.g. pancreas, liver"
                    className={inputCls}
                  />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT: Disease Context + Seed Targets (60%) */}
        <div className="flex-1 flex flex-col overflow-y-auto">
          <div className="px-6 pt-6 space-y-6 pb-6">

            {/* Disease Context — side-by-side */}
            <div>
              <SectionLabel>Disease Context</SectionLabel>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <FieldLabel required>Disease Name</FieldLabel>
                  <input
                    type="text"
                    value={disease}
                    onChange={(e) => setDisease(e.target.value)}
                    placeholder="e.g. Pancreatic Cancer"
                    required
                    className={inputCls}
                  />
                </div>
                <div>
                  <FieldLabel required hint="Open Targets ID">EFO ID</FieldLabel>
                  <input
                    type="text"
                    value={efoId}
                    onChange={(e) => setEfoId(e.target.value)}
                    placeholder="EFO_0000635"
                    required
                    className={`${inputCls} font-mono`}
                  />
                </div>
              </div>
            </div>

            {/* Seed Targets */}
            <div>
              <SectionLabel>Seed Targets</SectionLabel>
              <p className="text-[10px] text-[var(--color-on-surface-variant)]/70 mb-3 -mt-1">
                Known positive gene symbols — PU learning anchors
              </p>

              {/* Search input */}
              <div className="relative mb-3">
                <input
                  ref={inputRef}
                  type="text"
                  value={geneQuery}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (/[,;\s]/.test(val) && val.replace(/[,;\s]/g, '').length > 0) {
                      addGenes(val);
                    } else {
                      setGeneQuery(val);
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); if (geneQuery.trim()) addGene(geneQuery); }
                    if (e.key === 'Escape') setSuggestions([]);
                  }}
                  onPaste={(e) => {
                    const text = e.clipboardData.getData('text');
                    if (/[,;]/.test(text) || text.trim().includes(' ')) {
                      e.preventDefault();
                      addGenes(text);
                    }
                  }}
                  placeholder="Type a gene and press Enter — e.g. KRAS, TP53"
                  className={`${inputCls} pr-9`}
                />
                <span className="material-symbols-outlined text-[16px] text-[var(--color-on-surface-variant)] absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
                  search
                </span>
                {suggestions.length > 0 && (
                  <div
                    ref={suggestRef}
                    className="absolute top-full left-0 right-0 mt-1 bg-[var(--color-surface-container-high)] border border-[var(--color-outline-variant)] rounded shadow-xl z-50 overflow-hidden"
                  >
                    {suggestions.map((g) => (
                      <button
                        key={g}
                        type="button"
                        onMouseDown={(e) => { e.preventDefault(); addGene(g); }}
                        className="w-full px-4 py-2.5 text-left text-sm font-mono text-[var(--color-on-surface)] hover:bg-[var(--color-surface-container-highest)] transition-colors"
                      >
                        {g}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Gene tags — tall fixed area */}
              <div className="min-h-[120px] rounded border border-[var(--color-outline-variant)] bg-[var(--color-surface-container)] p-3">
                {seedGenes.length === 0 ? (
                  <p className="text-xs text-[var(--color-on-surface-variant)]/40 italic">
                    No seed genes added yet.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {seedGenes.map((g) => (
                      <span
                        key={g}
                        className="inline-flex items-center gap-1 pl-2.5 pr-1.5 py-1 rounded text-xs font-mono font-semibold border border-[var(--color-outline)] bg-[var(--color-surface-container-high)] text-[var(--color-on-surface)]"
                      >
                        {g}
                        <button
                          type="button"
                          onClick={() => removeGene(g)}
                          className="ml-0.5 rounded hover:text-[var(--color-error)] transition-colors p-0.5"
                        >
                          <span className="material-symbols-outlined text-[11px]">close</span>
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Seed SMILES — only relevant for explore / de_novo */}
            {intentMode !== 'repurpose' && (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-on-surface-variant)] mb-3">
                  Seed SMILES <span className="normal-case font-normal opacity-60">(optional)</span>
                </p>
                <p className="text-[10px] text-[var(--color-on-surface-variant)]/70 mb-3 -mt-1">
                  Known active compounds — seeds Phase 5 de novo generation. One SMILES per line or comma-separated.
                </p>
                <textarea
                  value={seedSmilesText}
                  onChange={(e) => setSeedSmilesText(e.target.value)}
                  placeholder={"CC(=O)Nc1ccc(O)cc1\nCc1ccc(S(N)(=O)=O)cc1\n..."}
                  rows={4}
                  className={`${inputCls} font-mono text-[11px] resize-y`}
                />
                {parsedSeedSmiles.length > 0 && (
                  <p className="text-[10px] text-[var(--color-primary-container)] mt-1">
                    {parsedSeedSmiles.length} valid SMILES parsed
                  </p>
                )}
              </div>
            )}

            {/* Error banner */}
            {error && (
              <div
                className="flex items-start gap-2.5 px-4 py-3 rounded border"
                style={{ background: 'rgba(255,85,85,0.06)', borderColor: 'rgba(255,85,85,0.2)' }}
              >
                <span
                  className="material-symbols-outlined text-[var(--color-error)] text-lg shrink-0 mt-0.5"
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  error
                </span>
                <p className="text-sm text-[var(--color-error)] leading-relaxed">{error}</p>
              </div>
            )}
          </div>
        </div>
      </form>

      {/* ── Sticky footer ────────────────────────────────────────────── */}
      <div className="shrink-0 flex items-center justify-between px-8 py-3 border-t border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)]">
        <div className="text-xs text-[var(--color-on-surface-variant)] space-y-0.5 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-[var(--color-on-surface-variant)]">{selectedMode.label}</span>
            <span className="text-[var(--color-outline)]">·</span>
            <span>P1 → P{throughPhase}</span>
            {disease && (
              <>
                <span className="text-[var(--color-outline)]">·</span>
                <span className="text-[var(--color-on-surface)] font-medium">{disease}</span>
                {efoId && <span className="font-mono text-[10px]">{efoId}</span>}
              </>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {seedGenes.length > 0 ? (
              <span>
                {seedGenes.length} seed gene{seedGenes.length !== 1 ? 's' : ''} · {seedGenes.slice(0, 4).join(', ')}
                {seedGenes.length > 4 ? ` +${seedGenes.length - 4}` : ''}
              </span>
            ) : (
              <span className="italic opacity-50">Add at least one seed gene to proceed</span>
            )}
            {parsedSeedSmiles.length > 0 && intentMode !== 'repurpose' && (
              <>
                <span className="text-[var(--color-outline)]">·</span>
                <span className="text-[var(--color-primary-container)]">
                  {parsedSeedSmiles.length} seed SMILES
                </span>
              </>
            )}
          </div>
        </div>

        <button
          type="submit"
          form="new-exp-form"
          disabled={!canSubmit}
          className="shrink-0 ml-6 flex items-center gap-2 px-6 py-2.5 rounded text-sm font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-[var(--color-primary-container)] text-[var(--color-on-primary)]"
        >
          {createRun.isPending ? (
            <>
              <span className="material-symbols-outlined text-[16px] animate-spin">progress_activity</span>
              Initializing…
            </>
          ) : (
            <>
              <span className="material-symbols-outlined text-[16px]">rocket_launch</span>
              Launch Pipeline
            </>
          )}
        </button>
      </div>
    </div>
  );
}

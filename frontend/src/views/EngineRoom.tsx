import { useEffect, useRef, useState, type ReactNode } from "react";
import { Search, X, Zap, Plus, AlertTriangle, Loader2 } from "lucide-react";
import { useStore } from "../store";
import { api } from "../lib/api";
import { cx } from "../lib/ui";

const INTENTS = [
  { key: "explore", label: "Explore", hint: "All phases" },
  { key: "de_novo", label: "De Novo", hint: "Design new molecules" },
  { key: "repurpose", label: "Repurpose", hint: "Existing drugs" },
];

const DEPTHS = [
  { v: 1, label: "Phase 1 · Target ID", hint: "Fast · fully local · validated" },
  { v: 2, label: "Through Phase 2 · Validation", hint: "+ structure / pockets (network)" },
  { v: 3, label: "Through Phase 3 · Modality", hint: "+ modality routing" },
];

function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/15 px-2 py-1 text-xs font-medium text-emerald-300 ring-1 ring-emerald-500/30">
      {label}
      <button onClick={onRemove} className="text-emerald-400/70 hover:text-emerald-200">
        <X size={12} />
      </button>
    </span>
  );
}

export default function EngineRoom() {
  const startRun = useStore((s) => s.startRun);
  const starting = useStore((s) => s.starting);
  const runError = useStore((s) => s.runError);
  const missingRequired = useStore((s) => s.missingRequired);

  const [disease, setDisease] = useState("pancreatic cancer");
  const [efo, setEfo] = useState("");
  const [intent, setIntent] = useState("explore");
  const [positives, setPositives] = useState<string[]>(["KRAS", "TP53", "SMAD4", "CDKN2A", "BRCA2"]);
  const [exclude, setExclude] = useState("");
  const [provider, setProvider] = useState("lmstudio");
  const [indication, setIndication] = useState("oncology");
  const [tissue, setTissue] = useState("Pancreas");
  const [maxTargets, setMaxTargets] = useState(20);
  const [nBags, setNBags] = useState(30);
  const [depth, setDepth] = useState(1);

  // gene search (debounced)
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);
  const debRef = useRef<number | null>(null);

  useEffect(() => {
    if (debRef.current) window.clearTimeout(debRef.current);
    if (!query.trim()) {
      setResults([]);
      return;
    }
    setSearching(true);
    debRef.current = window.setTimeout(async () => {
      try {
        const { results } = await api.get<{ results: string[] }>(
          `/genes?q=${encodeURIComponent(query.trim())}&limit=30`
        );
        setResults(results);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 200);
    return () => {
      if (debRef.current) window.clearTimeout(debRef.current);
    };
  }, [query]);

  const addGene = (g: string) => {
    if (!positives.includes(g)) setPositives([...positives, g]);
  };
  const removeGene = (g: string) => setPositives(positives.filter((x) => x !== g));

  const canRun = disease.trim().length > 0 && positives.length > 0 && !starting;

  const submit = () => {
    if (!canRun) return;
    startRun({
      disease: disease.trim(),
      disease_efo_id: efo.trim() || undefined,
      intent_mode: intent,
      known_positives: positives,
      exclude_targets: exclude
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      tissue_of_interest: tissue.trim() || "Lung",
      indication_type: indication,
      provider,
      target_count_max: maxTargets,
      pu_n_bags: nBags,
      through_phase: depth,
    });
  };

  return (
    <div className="h-full overflow-y-auto scroll-thin">
      <div className="mx-auto max-w-3xl px-6 py-8">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-zinc-100">Engine Room</h1>
          <p className="text-sm text-zinc-500">
            Configure a target-identification run. The PU model scores all ~19,700 genes by
            multi-omics similarity to your known positives.
          </p>
        </div>

        {/* Disease targeter */}
        <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
          Disease Targeter
        </label>
        <input
          value={disease}
          onChange={(e) => setDisease(e.target.value)}
          placeholder="Disease string, e.g. pancreatic cancer"
          className="w-full rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-3.5 text-lg text-zinc-100 placeholder-zinc-600 outline-none focus:border-emerald-500/60 focus:ring-2 focus:ring-emerald-500/20"
        />
        <input
          value={efo}
          onChange={(e) => setEfo(e.target.value)}
          placeholder="Optional EFO ID (e.g. EFO_0002618) — skips disease normalization"
          className="mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2 font-mono text-xs text-zinc-300 placeholder-zinc-600 outline-none focus:border-zinc-600"
        />

        {/* Intent toggles */}
        <div className="mt-6">
          <label className="mb-2 block text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
            Intent
          </label>
          <div className="flex flex-wrap gap-2">
            {INTENTS.map((it) => (
              <button
                key={it.key}
                onClick={() => setIntent(it.key)}
                className={cx(
                  "rounded-full px-4 py-2 text-sm font-medium ring-1 transition-colors",
                  intent === it.key
                    ? "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40"
                    : "bg-zinc-900 text-zinc-400 ring-zinc-700 hover:text-zinc-200"
                )}
                title={it.hint}
              >
                {it.label}
              </button>
            ))}
          </div>
        </div>

        {/* PU anchor dual-list */}
        <div className="mt-6">
          <label className="mb-2 block text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
            PU Learning Anchor{" "}
            <span className="ml-1 text-zinc-600 normal-case tracking-normal">
              — known positives (5–10 recommended)
            </span>
          </label>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {/* search */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
              <div className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-2">
                <Search size={14} className="text-zinc-500" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search HGNC genes…"
                  className="w-full bg-transparent text-sm text-zinc-200 placeholder-zinc-600 outline-none"
                />
                {searching && <Loader2 size={13} className="animate-spin text-zinc-500" />}
              </div>
              <div className="mt-2 h-44 overflow-y-auto scroll-thin">
                {results.length === 0 && (
                  <div className="px-1 py-6 text-center text-xs text-zinc-600">
                    {query ? "No matches" : "Type to search the gene universe"}
                  </div>
                )}
                {results.map((g) => {
                  const added = positives.includes(g);
                  return (
                    <button
                      key={g}
                      disabled={added}
                      onClick={() => addGene(g)}
                      className={cx(
                        "flex w-full items-center justify-between rounded-md px-2 py-1.5 font-mono text-xs",
                        added
                          ? "text-zinc-600"
                          : "text-zinc-300 hover:bg-zinc-800"
                      )}
                    >
                      {g}
                      {added ? (
                        <span className="text-[10px] text-emerald-500">added</span>
                      ) : (
                        <Plus size={12} className="text-zinc-500" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
            {/* selected */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
              <div className="mb-2 flex items-center justify-between text-xs text-zinc-400">
                <span>Known Positives</span>
                <span
                  className={cx(
                    "font-mono",
                    positives.length >= 5 ? "text-emerald-400" : "text-amber-400"
                  )}
                >
                  {positives.length}
                </span>
              </div>
              <div className="flex min-h-44 flex-wrap content-start gap-1.5">
                {positives.length === 0 && (
                  <div className="w-full px-1 py-6 text-center text-xs text-zinc-600">
                    Add at least one gene to anchor the model
                  </div>
                )}
                {positives.map((g) => (
                  <Chip key={g} label={g} onRemove={() => removeGene(g)} />
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Advanced */}
        <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-3">
          <Field label="Run depth">
            <select
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500/50"
            >
              {DEPTHS.map((d) => (
                <option key={d.v} value={d.v}>
                  {d.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[10px] text-zinc-600">{DEPTHS.find((d) => d.v === depth)?.hint}</p>
          </Field>
          <Field label="LLM provider">
            <Select value={provider} onChange={setProvider} options={["lmstudio", "anthropic", "openai"]} />
          </Field>
          <Field label="Indication">
            <Select value={indication} onChange={setIndication} options={["oncology", "chronic", "acute"]} />
          </Field>
          <Field label="Tissue of interest">
            <input
              value={tissue}
              onChange={(e) => setTissue(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500/50"
            />
          </Field>
          <Field label={`Max targets · ${maxTargets}`}>
            <input
              type="range"
              min={5}
              max={50}
              value={maxTargets}
              onChange={(e) => setMaxTargets(Number(e.target.value))}
              className="w-full accent-emerald-500"
            />
          </Field>
          <Field label={`PU bags · ${nBags}`}>
            <input
              type="range"
              min={10}
              max={60}
              step={5}
              value={nBags}
              onChange={(e) => setNBags(Number(e.target.value))}
              className="w-full accent-emerald-500"
            />
          </Field>
        </div>

        <div className="mt-4">
          <Field label="Exclude targets (comma-separated)">
            <input
              value={exclude}
              onChange={(e) => setExclude(e.target.value)}
              placeholder="e.g. MUC5B, ALB"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-2 font-mono text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/50"
            />
          </Field>
        </div>

        {/* errors */}
        {runError && (
          <div className="mt-5 flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-sm text-rose-300">
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
            <div>
              <div className="font-medium">{runError}</div>
              {missingRequired.length > 0 && (
                <div className="mt-1 text-xs text-rose-300/80">
                  Missing required: {missingRequired.join(", ")}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Initialize */}
        <div className="mt-6 flex justify-end">
          <button
            onClick={submit}
            disabled={!canRun}
            className={cx(
              "flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold transition-all",
              canRun
                ? "glow-emerald bg-emerald-500 text-zinc-950 hover:bg-emerald-400"
                : "cursor-not-allowed bg-zinc-800 text-zinc-600"
            )}
          >
            {starting ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
            {starting ? "Initializing…" : "Initialize Run"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-[11px] font-medium text-zinc-500">{label}</label>
      {children}
    </div>
  );
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-2 text-sm text-zinc-200 capitalize outline-none focus:border-emerald-500/50"
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}

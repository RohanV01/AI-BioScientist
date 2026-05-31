import type { ReactNode } from "react";
import { X } from "lucide-react";
import type { Target } from "../types";
import { cx, fmtNum } from "../lib/ui";

function prettyFeature(f: string): string {
  if (/^emb_\d+$/.test(f)) return `STRING dim ${f.slice(4)}`;
  const map: Record<string, string> = {
    chronos_median: "Essentiality (Chronos)",
    selective_fraction: "Selective-essential fraction",
    gtex_log_mean_tpm: "Expression (GTEx log-TPM)",
    gtex_pct_expressed: "Expression breadth",
    am_mean_pathogenicity: "AlphaMissense pathogenicity",
    am_high_path_fraction: "High-pathogenic fraction",
  };
  return map[f] || f;
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-lg bg-zinc-900/70 px-2.5 py-2 ring-1 ring-zinc-800">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="font-mono text-sm text-zinc-200">{value}</div>
    </div>
  );
}

export default function ShapDrawer({ target, onClose }: { target: Target | null; onClose: () => void }) {
  const open = !!target;
  const ev = target?.evidence_trail;
  const shap = ev?.shap_top || [];
  const maxAbs = Math.max(1e-6, ...shap.map((s) => Math.abs(s.value)));

  return (
    <>
      {/* backdrop */}
      <div
        className={cx(
          "absolute inset-0 z-10 bg-black/40 transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
      />
      <aside
        className={cx(
          "absolute right-0 top-0 z-20 h-full w-[420px] max-w-[90vw] border-l border-zinc-800 bg-zinc-950 shadow-2xl transition-transform duration-200",
          open ? "translate-x-0" : "translate-x-full"
        )}
      >
        {target && ev && (
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-lg font-semibold text-zinc-100">{target.symbol}</span>
                  <span className="text-xs text-zinc-500">rank #{target.rank}</span>
                </div>
                <div className="flex gap-1.5 pt-1">
                  {ev.is_master_regulator && (
                    <Badge className="bg-amber-500/15 text-amber-300 ring-amber-500/30">
                      Master Regulator
                    </Badge>
                  )}
                  {target.validation_score != null && (
                    <Badge
                      className={cx(
                        target.validation_score >= 0.5
                          ? "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30"
                          : "bg-rose-500/15 text-rose-300 ring-rose-500/30"
                      )}
                    >
                      validation {fmtNum(target.validation_score, 2)}
                    </Badge>
                  )}
                </div>
              </div>
              <button onClick={onClose} className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200">
                <X size={18} />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto scroll-thin px-4 py-4">
              {/* SHAP */}
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
                SHAP feature attributions
              </div>
              <div className="space-y-1.5">
                {shap.length === 0 && (
                  <div className="text-xs text-zinc-600">No SHAP values recorded for this gene.</div>
                )}
                {shap.map((s, i) => {
                  const pos = s.value >= 0;
                  const w = (Math.abs(s.value) / maxAbs) * 100;
                  return (
                    <div key={i} className="grid grid-cols-[1fr_auto] items-center gap-2">
                      <div>
                        <div className="mb-0.5 flex items-center justify-between">
                          <span className="truncate text-[11px] text-zinc-400">{prettyFeature(s.feature)}</span>
                        </div>
                        <div className="h-2 w-full rounded-full bg-zinc-800">
                          <div
                            className={cx("h-full rounded-full", pos ? "bg-emerald-500" : "bg-rose-500")}
                            style={{ width: `${w}%` }}
                          />
                        </div>
                      </div>
                      <span
                        className={cx(
                          "w-16 text-right font-mono text-[11px]",
                          pos ? "text-emerald-400" : "text-rose-400"
                        )}
                      >
                        {s.value >= 0 ? "+" : ""}
                        {fmtNum(s.value, 4)}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Evidence trail */}
              <div className="mb-2 mt-6 text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
                Evidence trail
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Stat label="PU probability" value={fmtNum(ev.xgb_probability ?? target.aggregate_score, 4)} />
                <Stat label="PU percentile" value={fmtNum((ev.pu_percentile ?? 0) * 100, 1) + "%"} />
                <Stat label="DoRothEA activity" value={fmtNum(ev.dorothea_activity, 3)} />
                <Stat label="Regulon size" value={ev.regulon_size ?? 0} />
                <Stat label="Essentiality (Chronos)" value={fmtNum(ev.essentiality, 3)} />
                <Stat label="Selective frac" value={fmtNum(ev.selective_fraction, 3)} />
                <Stat label="Expression (GTEx)" value={fmtNum(ev.expression, 3)} />
                <Stat label="Genetic" value={fmtNum(ev.genetic, 3)} />
                <Stat label="Tractability" value={fmtNum(ev.tractability, 3)} />
                <Stat label="PPI centrality" value={fmtNum(ev.ppi_eigenvector, 3)} />
              </div>

              {(target.modality_primary && target.modality_primary !== "unknown") && (
                <div className="mt-4 rounded-lg bg-zinc-900/70 px-3 py-2 ring-1 ring-zinc-800">
                  <div className="text-[10px] uppercase tracking-wide text-zinc-500">Modality</div>
                  <div className="text-sm text-zinc-200">
                    {target.modality_primary}
                    {target.modality_secondary ? ` / ${target.modality_secondary}` : ""}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </aside>
    </>
  );
}

function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cx("rounded px-1.5 py-0.5 text-[10px] font-medium ring-1", className)}>{children}</span>
  );
}

import { FlaskConical, Lock, Hexagon } from "lucide-react";
import { useStore } from "../store";
import { cx } from "../lib/ui";

const ADMET_AXES = ["Toxicity", "Clearance", "Bioavailability", "Lipophilicity", "MW"];

export default function MoleculeStudio() {
  const targets = useStore((s) => s.targets);
  const routed = targets.filter((t) => t.modality_primary && t.modality_primary !== "unknown");

  return (
    <div className="flex h-full flex-col p-4">
      <div className="mb-3 flex items-center gap-2">
        <FlaskConical size={16} className="text-emerald-400" />
        <h2 className="text-sm font-medium text-zinc-200">Molecule Studio</h2>
        <span className="flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-400">
          <Lock size={10} /> Phases 5–9 not yet implemented
        </span>
      </div>

      {/* Top half — roster */}
      <div className="min-h-0 flex-1 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
        <div className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
          Generated Compound Roster
        </div>
        {routed.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <Hexagon size={40} className="mb-3 text-zinc-700" />
            <div className="text-zinc-400">No molecules generated</div>
            <div className="mt-1 max-w-md text-sm text-zinc-600">
              This studio renders de novo compounds (2D SMILES, Boltz-2 binding affinity, unified
              ADMET) once the generative phases land. Run a pipeline through Phase 3 to route
              targets to a modality first.
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {routed.map((t) => (
              <div
                key={t.rank}
                className="rounded-lg border border-dashed border-zinc-700 bg-zinc-900/60 p-3"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-sm font-semibold text-zinc-200">{t.symbol}</span>
                  <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-emerald-300">
                    {t.modality_primary}
                  </span>
                </div>
                <div className="mt-6 flex items-center justify-center text-[11px] text-zinc-600">
                  awaiting design
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Bottom half — deep dive / radar placeholder */}
      <div className="mt-3 h-48 shrink-0 rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
        <div className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
          ADMET Deep Dive
        </div>
        <div className="flex h-full items-center gap-6">
          <RadarPlaceholder />
          <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-3">
            {ADMET_AXES.map((a) => (
              <div key={a} className="rounded-lg bg-zinc-900/70 px-3 py-2 ring-1 ring-zinc-800">
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">{a}</div>
                <div className="font-mono text-sm text-zinc-600">—</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function RadarPlaceholder() {
  // Decorative pentagon (5 ADMET axes) — populated once Phase 7 MPO emits scores.
  const cx0 = 60,
    cy0 = 60,
    r = 46;
  const pts = Array.from({ length: 5 }, (_, i) => {
    const a = (Math.PI * 2 * i) / 5 - Math.PI / 2;
    return [cx0 + r * Math.cos(a), cy0 + r * Math.sin(a)];
  });
  const poly = pts.map((p) => p.join(",")).join(" ");
  return (
    <svg width={120} height={120} className="shrink-0">
      <polygon points={poly} fill="none" stroke="#3f3f46" strokeWidth={1} />
      <polygon
        points={pts.map((p) => [cx0 + (p[0] - cx0) * 0.5, cy0 + (p[1] - cy0) * 0.5].join(",")).join(" ")}
        fill="none"
        stroke="#27272a"
        strokeWidth={1}
      />
      {pts.map((p, i) => (
        <line key={i} x1={cx0} y1={cy0} x2={p[0]} y2={p[1]} stroke="#27272a" strokeWidth={1} />
      ))}
    </svg>
  );
}

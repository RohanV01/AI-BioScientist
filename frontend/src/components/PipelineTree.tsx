import { Check, Loader2, X, Minus } from "lucide-react";
import { useStore } from "../store";
import { cx, PHASE_STYLE } from "../lib/ui";
import type { PhaseStatus } from "../types";

function StatusIcon({ status }: { status: PhaseStatus }) {
  if (status === "completed") return <Check size={11} className="text-zinc-950" />;
  if (status === "running") return <Loader2 size={11} className="text-zinc-950 animate-spin" />;
  if (status === "failed") return <X size={11} className="text-zinc-950" />;
  return <Minus size={10} className="text-zinc-500" />;
}

export default function PipelineTree() {
  const phases = useStore((s) => s.phases);
  const setView = useStore((s) => s.setView);
  const targets = useStore((s) => s.targets);

  return (
    <div className="space-y-0.5">
      <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold mb-2">
        Pipeline · 9 Phases
      </div>
      {phases.map((p, i) => {
        const style = PHASE_STYLE[p.status];
        const isLast = i === phases.length - 1;
        const clickable = p.phase >= 1 && p.phase <= 3 && targets.length > 0;
        return (
          <div
            key={p.phase}
            className={cx(
              "relative flex items-start gap-2.5 rounded-md px-1.5 py-1",
              clickable && "cursor-pointer hover:bg-zinc-800/60"
            )}
            onClick={clickable ? () => setView("scorecard") : undefined}
          >
            {/* connector */}
            {!isLast && (
              <span
                className={cx(
                  "absolute left-[12px] top-[22px] h-[18px] w-px",
                  p.status === "completed" ? "bg-emerald-600/50" : "bg-zinc-800"
                )}
              />
            )}
            <span
              className={cx(
                "mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full ring-1",
                style.ring,
                style.dot
              )}
            >
              <StatusIcon status={p.status} />
            </span>
            <div className="min-w-0 flex-1 leading-tight">
              <div className={cx("text-xs font-medium truncate", style.text)}>
                <span className="text-zinc-600 mr-1">{p.phase}</span>
                {p.name}
              </div>
              <div className="text-[10px] text-zinc-600 capitalize">
                {p.status.replace("_", " ")}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

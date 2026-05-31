import { useEffect, useMemo, useRef, useState } from "react";
import { TerminalSquare, Activity } from "lucide-react";
import { useStore } from "../store";
import { cx, LOG_LEVEL_COLOR, shortTime, fmtNum } from "../lib/ui";

const METRIC_ORDER = [
  "universe",
  "genes",
  "features",
  "string_dims",
  "positives",
  "bags",
  "auroc",
  "targets",
  "validated",
  "passed",
];

function MetricTile({ label, value, unit }: { label: string; value: number; unit: string }) {
  const display = Number.isInteger(value) ? value.toLocaleString() : fmtNum(value, 3);
  return (
    <div className="min-w-[120px] flex-1 rounded-lg border border-zinc-800 bg-zinc-900/70 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="font-mono text-lg font-semibold text-emerald-300">
        {display}
        {unit && <span className="ml-1 text-xs text-zinc-500">{unit}</span>}
      </div>
    </div>
  );
}

export default function MatrixView() {
  const logs = useStore((s) => s.logs);
  const metrics = useStore((s) => s.metrics);
  const phases = useStore((s) => s.phases);
  const runState = useStore((s) => s.runState);
  const activeRunId = useStore((s) => s.activeRunId);
  const activeDisease = useStore((s) => s.activeDisease);

  const scrollRef = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);

  // auto-scroll to newest line unless the user scrolled up
  useEffect(() => {
    if (follow && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, follow]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
    setFollow(nearBottom);
  };

  const tiles = useMemo(
    () => METRIC_ORDER.map((k) => metrics[k]).filter(Boolean),
    [metrics]
  );

  const activePhases = phases.filter((p) => p.phase <= 3);

  if (!activeRunId) {
    return (
      <Empty />
    );
  }

  return (
    <div className="flex h-full flex-col p-4">
      {/* header + inline stepper */}
      <div className="mb-3 flex items-center gap-3">
        <Activity size={16} className="text-emerald-400" />
        <span className="text-sm font-medium text-zinc-200 capitalize">{activeDisease || "Run"}</span>
        <div className="ml-2 flex items-center gap-1.5">
          {activePhases.map((p) => (
            <span
              key={p.phase}
              title={`${p.phase} · ${p.name} — ${p.status}`}
              className={cx(
                "h-1.5 w-8 rounded-full",
                p.status === "completed"
                  ? "bg-emerald-500"
                  : p.status === "running"
                  ? "bg-amber-400 animate-softpulse"
                  : p.status === "failed"
                  ? "bg-rose-500"
                  : "bg-zinc-700"
              )}
            />
          ))}
        </div>
        <span className="ml-auto font-mono text-xs text-zinc-500">{logs.length} lines</span>
      </div>

      {/* micro-metrics */}
      {tiles.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {tiles.map((m) => (
            <MetricTile key={m.key} label={m.label} value={m.value} unit={m.unit} />
          ))}
        </div>
      )}

      {/* terminal */}
      <div className="relative min-h-0 flex-1 overflow-hidden rounded-xl border border-zinc-800 bg-black/60">
        <div className="flex items-center gap-2 border-b border-zinc-800 bg-zinc-900/70 px-3 py-1.5">
          <TerminalSquare size={13} className="text-zinc-500" />
          <span className="font-mono text-[11px] text-zinc-500">backend://pipeline/stdout</span>
          {!follow && (
            <button
              onClick={() => {
                setFollow(true);
                if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
              }}
              className="ml-auto rounded bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-300 hover:bg-zinc-700"
            >
              ↓ Follow
            </button>
          )}
        </div>
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="h-full overflow-y-auto scroll-thin px-3 py-2 pb-10 font-mono text-[12px] leading-[1.5]"
        >
          {logs.length === 0 && (
            <div className="py-6 text-zinc-600">Waiting for backend output…</div>
          )}
          {logs.map((l) => (
            <div key={l.seq} className="flex gap-2 whitespace-pre-wrap break-words">
              <span className="shrink-0 text-zinc-600">{shortTime(l.ts)}</span>
              <span className={cx("min-w-0", LOG_LEVEL_COLOR[l.level] || "text-zinc-300")}>
                <span className="text-zinc-600">{l.logger.replace("src.phases.", "")} </span>
                {l.message}
              </span>
            </div>
          ))}
          {runState === "running" && (
            <div className="text-emerald-400 cursor-blink" />
          )}
        </div>
      </div>
    </div>
  );
}

function Empty() {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <TerminalSquare size={40} className="mb-3 text-zinc-700" />
      <div className="text-zinc-400">No active run</div>
      <div className="mt-1 text-sm text-zinc-600">
        Initialize a run in the Engine Room to watch every step stream here live.
      </div>
    </div>
  );
}

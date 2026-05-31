import { Dna, Plus, RefreshCw, Circle } from "lucide-react";
import { useStore } from "../store";
import { cx } from "../lib/ui";
import PipelineTree from "./PipelineTree";
import Telemetry from "./Telemetry";

const RUN_STATUS_COLOR: Record<string, string> = {
  completed: "text-emerald-400",
  running: "text-amber-300",
  failed: "text-rose-400",
  pending: "text-zinc-400",
};

function RunRow({ id }: { id: string }) {
  const run = useStore((s) => s.runs.find((r) => r.id === id))!;
  const active = useStore((s) => s.activeRunId === id);
  const openRun = useStore((s) => s.openRun);
  const live = run.running || run.status === "running";
  return (
    <button
      onClick={() => openRun(id)}
      className={cx(
        "w-full text-left rounded-md px-2.5 py-1.5 transition-colors group",
        active ? "bg-zinc-800 ring-1 ring-zinc-700" : "hover:bg-zinc-800/50"
      )}
    >
      <div className="flex items-center gap-2">
        <Circle
          size={7}
          className={cx(
            "shrink-0 fill-current",
            RUN_STATUS_COLOR[run.status] || "text-zinc-500",
            live && "animate-softpulse"
          )}
        />
        <span className="truncate text-xs font-medium text-zinc-200 capitalize">
          {run.disease_name}
        </span>
      </div>
      <div className="ml-[15px] flex items-center gap-2 text-[10px] text-zinc-500">
        <span className="capitalize">{run.intent_mode}</span>
        <span>·</span>
        <span>P{run.current_phase}</span>
        <span>·</span>
        <span className={cx("capitalize", RUN_STATUS_COLOR[run.status])}>{run.status}</span>
      </div>
    </button>
  );
}

export default function Sidebar() {
  const runs = useStore((s) => s.runs);
  const setView = useStore((s) => s.setView);
  const loadRuns = useStore((s) => s.loadRuns);
  const streamOpen = useStore((s) => s.streamOpen);
  const runState = useStore((s) => s.runState);

  return (
    <aside className="flex h-screen w-72 shrink-0 flex-col border-r border-zinc-800 bg-zinc-900/60">
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-4 py-3.5 border-b border-zinc-800">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-400">
          <Dna size={18} />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold text-zinc-100">Discovery Studio</div>
          <div className="text-[10px] text-zinc-500">In-Silico Target Engine</div>
        </div>
        <span
          className={cx(
            "ml-auto h-2 w-2 rounded-full",
            streamOpen ? "bg-emerald-500" : runState === "running" ? "bg-amber-400" : "bg-zinc-600"
          )}
          title={streamOpen ? "Live stream connected" : "Idle"}
        />
      </div>

      {/* New run */}
      <div className="px-3 py-3">
        <button
          onClick={() => setView("engine")}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-zinc-800 px-3 py-2 text-sm font-medium text-zinc-100 ring-1 ring-zinc-700 hover:bg-zinc-700/70 transition-colors"
        >
          <Plus size={15} /> New Run
        </button>
      </div>

      {/* Scrollable middle: runs + pipeline tree */}
      <div className="flex-1 overflow-y-auto scroll-thin px-3 pb-3 space-y-5">
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold">
              Runs
            </span>
            <button
              onClick={() => loadRuns()}
              className="text-zinc-500 hover:text-zinc-300"
              title="Refresh runs"
            >
              <RefreshCw size={12} />
            </button>
          </div>
          <div className="space-y-0.5">
            {runs.length === 0 && (
              <div className="text-[11px] text-zinc-600 px-2 py-3">
                No runs yet. Start one in the Engine Room.
              </div>
            )}
            {runs.map((r) => (
              <RunRow key={r.id} id={r.id} />
            ))}
          </div>
        </div>

        <PipelineTree />
      </div>

      {/* Telemetry pinned at the bottom */}
      <div className="border-t border-zinc-800 px-4 py-3">
        <Telemetry />
      </div>
    </aside>
  );
}

import { useEffect, type ReactNode } from "react";
import { SlidersHorizontal, TerminalSquare, Table2, FlaskConical } from "lucide-react";
import { useStore } from "./store";
import { cx } from "./lib/ui";
import type { ViewKey } from "./types";
import Sidebar from "./components/Sidebar";
import EngineRoom from "./views/EngineRoom";
import MatrixView from "./views/MatrixView";
import Scorecard from "./views/Scorecard";
import MoleculeStudio from "./views/MoleculeStudio";

const TABS: { key: ViewKey; label: string; icon: ReactNode }[] = [
  { key: "engine", label: "Engine Room", icon: <SlidersHorizontal size={15} /> },
  { key: "matrix", label: "The Matrix", icon: <TerminalSquare size={15} /> },
  { key: "scorecard", label: "Target Scorecard", icon: <Table2 size={15} /> },
  { key: "studio", label: "Molecule Studio", icon: <FlaskConical size={15} /> },
];

const RUN_PILL: Record<string, string> = {
  idle: "bg-zinc-800 text-zinc-400 ring-zinc-700",
  running: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  completed: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  failed: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
};

export default function App() {
  const view = useStore((s) => s.view);
  const setView = useStore((s) => s.setView);
  const loadRuns = useStore((s) => s.loadRuns);
  const startTelemetryPoll = useStore((s) => s.startTelemetryPoll);
  const runState = useStore((s) => s.runState);
  const activeDisease = useStore((s) => s.activeDisease);

  useEffect(() => {
    loadRuns();
    const stop = startTelemetryPoll();
    return stop;
  }, [loadRuns, startTelemetryPoll]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-zinc-950 text-zinc-200">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col">
        {/* Top tab bar */}
        <header className="flex items-center gap-1 border-b border-zinc-800 bg-zinc-900/40 px-3">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setView(t.key)}
              className={cx(
                "flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors",
                view === t.key
                  ? "border-emerald-500 text-zinc-100"
                  : "border-transparent text-zinc-500 hover:text-zinc-300"
              )}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-3 pr-2">
            {activeDisease && (
              <span className="text-xs text-zinc-400 capitalize hidden md:block">
                {activeDisease}
              </span>
            )}
            <span
              className={cx(
                "rounded-full px-2.5 py-1 text-[11px] font-medium capitalize ring-1",
                RUN_PILL[runState]
              )}
            >
              {runState}
            </span>
          </div>
        </header>

        {/* Active view */}
        <div className="min-h-0 flex-1 overflow-hidden">
          {view === "engine" && <EngineRoom />}
          {view === "matrix" && <MatrixView />}
          {view === "scorecard" && <Scorecard />}
          {view === "studio" && <MoleculeStudio />}
        </div>
      </main>
    </div>
  );
}

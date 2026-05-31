import { useMemo, useRef, useState, type ReactNode } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowUpDown, Table2, RefreshCw } from "lucide-react";
import { useStore } from "../store";
import { cx, fmtNum } from "../lib/ui";
import type { Target } from "../types";
import ShapDrawer from "../components/ShapDrawer";

const GRID = "56px minmax(150px,1.6fr) 1fr 1fr 1fr 0.9fr 0.9fr 1.1fr";

function puColor(v: number): string {
  if (v >= 0.9) return "text-emerald-300";
  if (v >= 0.6) return "text-amber-200";
  return "text-zinc-400";
}
function essColor(v: number): string {
  if (v <= -0.5) return "text-emerald-300"; // strong dependency
  if (v < 0) return "text-amber-200";
  return "text-zinc-500";
}

function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cx("rounded px-1 py-px text-[9px] font-semibold uppercase ring-1", className)}>
      {children}
    </span>
  );
}

export default function Scorecard() {
  const targets = useStore((s) => s.targets);
  const selectedRank = useStore((s) => s.selectedRank);
  const setSelected = useStore((s) => s.setSelected);
  const fetchTargets = useStore((s) => s.fetchTargets);
  const activeRunId = useStore((s) => s.activeRunId);
  const [sorting, setSorting] = useState<SortingState>([{ id: "pu", desc: true }]);

  const columns = useMemo<ColumnDef<Target>[]>(
    () => [
      {
        id: "rank",
        header: "#",
        accessorKey: "rank",
        cell: (c) => <span className="font-mono text-zinc-500">{c.row.original.rank}</span>,
      },
      {
        id: "symbol",
        header: "Gene",
        accessorKey: "symbol",
        cell: (c) => {
          const t = c.row.original;
          const ev = t.evidence_trail || {};
          return (
            <div className="flex items-center gap-1.5">
              <span className="font-mono font-semibold text-zinc-100">{t.symbol}</span>
              {ev.is_master_regulator && (
                <Badge className="bg-amber-500/15 text-amber-300 ring-amber-500/30">MR</Badge>
              )}
              {(ev.essentiality ?? 0) <= -0.5 && (
                <Badge className="bg-emerald-500/15 text-emerald-300 ring-emerald-500/30">ESS</Badge>
              )}
              {t.validation_score != null && t.validation_score >= 0.5 && (
                <Badge className="bg-emerald-500/15 text-emerald-300 ring-emerald-500/30">VAL</Badge>
              )}
            </div>
          );
        },
      },
      {
        id: "pu",
        header: "PU Prob",
        accessorFn: (r) => r.evidence_trail?.xgb_probability ?? r.aggregate_score ?? 0,
        cell: (c) => {
          const v = c.getValue<number>();
          return <span className={cx("font-mono", puColor(v))}>{fmtNum(v, 3)}</span>;
        },
      },
      {
        id: "dorothea",
        header: "DoRothEA",
        accessorFn: (r) => r.evidence_trail?.dorothea_activity ?? 0,
        cell: (c) => <span className="font-mono text-zinc-300">{fmtNum(c.getValue<number>(), 3)}</span>,
      },
      {
        id: "ess",
        header: "Essentiality",
        accessorFn: (r) => r.evidence_trail?.essentiality ?? 0,
        cell: (c) => {
          const v = c.getValue<number>();
          return <span className={cx("font-mono", essColor(v))}>{fmtNum(v, 3)}</span>;
        },
      },
      {
        id: "genetic",
        header: "Genetic",
        accessorFn: (r) => r.evidence_trail?.genetic ?? 0,
        cell: (c) => <span className="font-mono text-zinc-300">{fmtNum(c.getValue<number>(), 2)}</span>,
      },
      {
        id: "tract",
        header: "Tract.",
        accessorFn: (r) => r.evidence_trail?.tractability ?? 0,
        cell: (c) => <span className="font-mono text-zinc-300">{fmtNum(c.getValue<number>(), 2)}</span>,
      },
      {
        id: "modality",
        header: "Modality",
        accessorFn: (r) => r.modality_primary || "—",
        cell: (c) => {
          const v = c.getValue<string>();
          return (
            <span className="text-xs text-zinc-300">
              {v && v !== "unknown" ? v : <span className="text-zinc-600">pending</span>}
            </span>
          );
        },
      },
    ],
    []
  );

  const table = useReactTable({
    data: targets,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const rows = table.getRowModel().rows;
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 42,
    overscan: 14,
  });

  const selected = targets.find((t) => t.rank === selectedRank) || null;

  return (
    <div className="relative flex h-full flex-col">
      <div className="flex items-center gap-3 px-4 py-3">
        <Table2 size={16} className="text-emerald-400" />
        <h2 className="text-sm font-medium text-zinc-200">Target Scorecard</h2>
        <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">
          {targets.length} targets
        </span>
        <button
          onClick={() => fetchTargets()}
          className="ml-auto flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
        >
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {targets.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center text-center">
          <Table2 size={40} className="mb-3 text-zinc-700" />
          <div className="text-zinc-400">No ranked targets yet</div>
          <div className="mt-1 text-sm text-zinc-600">
            {activeRunId ? "Phase 1 is still running — results appear here when ready." : "Start a run in the Engine Room."}
          </div>
        </div>
      ) : (
        <div className="min-h-0 flex-1 px-4 pb-4">
          <div className="flex h-full flex-col overflow-hidden rounded-xl border border-zinc-800">
            {/* header */}
            <div
              className="grid shrink-0 border-b border-zinc-800 bg-zinc-900/80 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500"
              style={{ gridTemplateColumns: GRID }}
            >
              {table.getHeaderGroups()[0].headers.map((h) => (
                <button
                  key={h.id}
                  onClick={h.column.getToggleSortingHandler()}
                  className="flex items-center gap-1 text-left hover:text-zinc-300"
                >
                  {flexRender(h.column.columnDef.header, h.getContext())}
                  {h.column.getCanSort() && <ArrowUpDown size={10} className="opacity-50" />}
                  {{ asc: " ↑", desc: " ↓" }[h.column.getIsSorted() as string] || ""}
                </button>
              ))}
            </div>
            {/* virtualized body */}
            <div ref={parentRef} className="min-h-0 flex-1 overflow-y-auto scroll-thin">
              <div style={{ height: `${virtualizer.getTotalSize()}px`, position: "relative" }}>
                {virtualizer.getVirtualItems().map((vi) => {
                  const row = rows[vi.index];
                  const t = row.original;
                  const isSel = t.rank === selectedRank;
                  return (
                    <div
                      key={row.id}
                      onClick={() => setSelected(isSel ? null : t.rank)}
                      className={cx(
                        "absolute left-0 top-0 grid w-full cursor-pointer items-center px-3 text-sm",
                        isSel ? "bg-emerald-500/10" : vi.index % 2 ? "bg-zinc-900/30" : "",
                        "hover:bg-zinc-800/60"
                      )}
                      style={{
                        gridTemplateColumns: GRID,
                        height: `${vi.size}px`,
                        transform: `translateY(${vi.start}px)`,
                      }}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <div key={cell.id} className="truncate pr-2">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      <ShapDrawer target={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

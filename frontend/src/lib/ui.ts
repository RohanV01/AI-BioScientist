import type { PhaseStatus } from "../types";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function fmtNum(n: number | null | undefined, digits = 3): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 1000) return n.toLocaleString();
  return Number(n.toFixed(digits)).toString();
}

export function fmtPct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${Math.round(n)}%`;
}

export function shortTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("en-GB", { hour12: false });
}

/** Tailwind classes for each phase status (dot + label colours). */
export const PHASE_STYLE: Record<PhaseStatus, { dot: string; text: string; ring: string }> = {
  completed: { dot: "bg-emerald-500", text: "text-emerald-300", ring: "ring-emerald-500/30" },
  running: { dot: "bg-amber-400 animate-softpulse", text: "text-amber-200", ring: "ring-amber-400/40" },
  failed: { dot: "bg-rose-500", text: "text-rose-300", ring: "ring-rose-500/30" },
  pending: { dot: "bg-zinc-600", text: "text-zinc-400", ring: "ring-zinc-700" },
  skipped: { dot: "bg-zinc-700", text: "text-zinc-500", ring: "ring-zinc-800" },
  not_implemented: { dot: "bg-zinc-800", text: "text-zinc-600", ring: "ring-zinc-800" },
};

/** Colour a utilisation bar by load: emerald < 70%, amber < 88%, rose above. */
export function loadColor(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return "bg-zinc-600";
  if (pct >= 88) return "bg-rose-500";
  if (pct >= 70) return "bg-amber-400";
  return "bg-emerald-500";
}

export const LOG_LEVEL_COLOR: Record<string, string> = {
  INFO: "text-zinc-300",
  WARNING: "text-amber-300",
  ERROR: "text-rose-400",
  DEBUG: "text-zinc-500",
};

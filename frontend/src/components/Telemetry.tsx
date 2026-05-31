import type { ReactNode } from "react";
import { Cpu, MemoryStick, Gauge as GaugeIcon } from "lucide-react";
import { useStore } from "../store";
import { cx, fmtPct, loadColor } from "../lib/ui";

function Gauge({
  icon,
  label,
  used,
  total,
  unit,
  pct,
}: {
  icon: ReactNode;
  label: string;
  used?: number | null;
  total?: number | null;
  unit: string;
  pct?: number | null;
}) {
  const width = pct === null || pct === undefined ? 0 : Math.min(100, pct);
  const detail =
    used !== null && used !== undefined && total !== null && total !== undefined
      ? `${used} / ${total} ${unit}`
      : "—";
  return (
    <div>
      <div className="flex items-center justify-between text-[11px] mb-1">
        <span className="flex items-center gap-1.5 text-zinc-400">
          {icon}
          {label}
        </span>
        <span className="font-mono text-zinc-300">{fmtPct(pct)}</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
        <div
          className={cx("h-full rounded-full transition-all duration-500", loadColor(pct))}
          style={{ width: `${width}%` }}
        />
      </div>
      <div className="mt-0.5 text-[10px] font-mono text-zinc-500">{detail}</div>
    </div>
  );
}

export default function Telemetry() {
  const t = useStore((s) => s.telemetry);
  return (
    <div className="space-y-3">
      <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold">
        Hardware Telemetry
      </div>
      <Gauge
        icon={<MemoryStick size={12} />}
        label="RAM"
        used={t.ram_used_gb}
        total={t.ram_total_gb}
        unit="GB"
        pct={t.ram_pct}
      />
      <Gauge
        icon={<GaugeIcon size={12} />}
        label="VRAM"
        used={t.vram_used_mb}
        total={t.vram_total_mb}
        unit="MB"
        pct={t.vram_pct}
      />
      <Gauge icon={<Cpu size={12} />} label="CPU" unit="" pct={t.cpu_pct} />
    </div>
  );
}

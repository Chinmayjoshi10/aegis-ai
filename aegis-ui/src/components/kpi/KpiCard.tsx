"use client";

import { cn } from "@/lib/utils";
import { SignalBadge } from "@/components/ui/SignalBadge";
import { useAegisStore } from "@/store/aegisStore";
import type { KpiData } from "@/lib/types";

export function KpiCard({ data }: { data: KpiData }) {
  const { focusId, setFocus } = useAegisStore();
  const dimmed = focusId !== null && focusId !== data.id;
  const focused = focusId === data.id;

  return (
    <div
      onClick={() => setFocus(focusId === data.id ? null : data.id)}
      className={cn(
        "card p-4 flex flex-col cursor-pointer transition-all duration-200",
        dimmed && "focus-dimmed",
        focused && "focus-active"
      )}
    >
      <span className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8]">{data.metric}</span>
      <div className="flex items-baseline gap-2 mt-1">
        <span className="text-2xl font-medium font-mono tabular-nums text-[#F8FAFC]">{data.value}</span>
        <span className={cn("text-xs font-mono tabular-nums", data.deltaDirection === "up" ? "text-emerald-400" : data.deltaDirection === "down" ? "text-red-400" : "text-slate-500")}>
          {data.delta}
        </span>
      </div>
      {data.signal && (
        <div className="mt-3 pt-3 border-t border-[#2A2F3A]">
          <SignalBadge direction={data.signal.direction} type={data.signal.type} />
        </div>
      )}
    </div>
  );
}

export function KpiGrid({ kpis }: { kpis: KpiData[] }) {
  return (
    <div className="grid grid-cols-5 gap-4 stagger-children">
      {kpis.map((kpi) => (
        <KpiCard key={kpi.id} data={kpi} />
      ))}
    </div>
  );
}

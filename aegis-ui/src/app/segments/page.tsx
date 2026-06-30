"use client";

import { AppShell } from "@/components/layout/AppShell";
import { PriorityBadge } from "@/components/ui/PriorityBadge";
import { VisualConfidence } from "@/components/ui/VisualConfidence";
import { mockSegments } from "@/lib/mockData";
import { useAegisStore } from "@/store/aegisStore";
import { cn } from "@/lib/utils";
import { useState, useEffect } from "react";
import { RefreshCw, Upload } from "lucide-react";

const segTypes = ["All", "Channel", "Campaign", "Region", "Product", "Cohort"];

export default function SegmentsPage() {
  const segments = useAegisStore((s) => s.segments);
  const rawAnalysis = useAegisStore((s) => s.rawAnalysis);
  const setRawAnalysis = useAegisStore((s) => s.setRawAnalysis);

  const hasData = rawAnalysis !== null && segments.length > 0;
  const allSegments = hasData ? segments : mockSegments;

  const [activeType, setActiveType] = useState("All");
  const [selected, setSelected] = useState(allSegments[0]);
  const filtered = activeType === "All" ? allSegments : allSegments.filter((s) => s.type.toLowerCase() === activeType.toLowerCase());

  // Re-sync selected when live segments change after a new upload
  useEffect(() => {
    if (allSegments.length > 0) {
      setSelected(allSegments[0]);
      setActiveType("All");
    }
  }, [rawAnalysis]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <AppShell>
      <div className="grid grid-cols-12 gap-6 h-full">
        <div className="col-span-8 space-y-6 overflow-y-auto">
          <div>
            <div className="flex items-start justify-between">
              <div>
                <h1 className="text-xl font-semibold mb-1">Segment Explorer</h1>
                <p className="text-sm text-[#64748B]">
                  {hasData
                    ? "Live segment analysis from your uploaded data."
                    : "Cross-segment analysis with AI-generated narratives and decision linkage."}
                </p>
              </div>
              {hasData && (
                <button
                  onClick={() => {
                    setRawAnalysis(null);
                    useAegisStore.setState({ segments: [], kpis: [], decisions: [], chartData: [], narration: null });
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-mono border border-[#2A2F3A] text-[#94A3B8] rounded hover:border-[#A855F7]/50 hover:text-[#A855F7] transition-colors"
                >
                  <Upload className="w-3 h-3" />
                  Analyse New CSV
                </button>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {segTypes.map((t) => (
              <button key={t} onClick={() => setActiveType(t)} className={cn("px-3 py-1.5 text-[11px] font-mono rounded transition-all", activeType === t ? "bg-[#A855F7]/10 text-[#A855F7] border border-[#A855F7]/30" : "text-[#64748B] border border-[#2A2F3A] hover:text-[#94A3B8]")}>
                {t}
              </button>
            ))}
            {hasData && (
              <span className="ml-auto text-[9px] font-mono text-emerald-400 border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 rounded">LIVE DATA</span>
            )}
          </div>

          {/* Treemap */}
          <div className="card p-4">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-3">Performance Map</h3>
            <div className="grid grid-cols-6 gap-1 h-32">
              {filtered.map((seg) => {
                const revenue = parseInt(seg.revenue.replace(/[$KM,]/g, "")) || 1;
                const span = Math.max(1, Math.round(revenue / 500));
                const colors = { up: "bg-emerald-500/20 border-emerald-500/30 hover:bg-emerald-500/30", down: "bg-red-500/20 border-red-500/30 hover:bg-red-500/30", flat: "bg-slate-500/20 border-slate-500/30 hover:bg-slate-500/30" };
                return (
                  <button key={seg.id} onClick={() => setSelected(seg)} className={cn("rounded border text-[10px] font-mono flex items-center justify-center transition-all cursor-pointer p-1", colors[seg.growthDirection], selected?.id === seg.id && "ring-2 ring-[#A855F7]")} style={{ gridColumn: `span ${Math.min(span, 3)}` }}>
                    {seg.name}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Comparison Table */}
          <div className="card overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[#2A2F3A] text-[#64748B]">
                  <th className="text-left px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Segment</th>
                  <th className="text-right px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Revenue</th>
                  <th className="text-right px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Growth</th>
                  <th className="text-right px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Confidence</th>
                  <th className="text-right px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Signals</th>
                  <th className="text-center px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Priority</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((seg) => (
                  <tr key={seg.id} onClick={() => setSelected(seg)} className={cn("border-b border-[#2A2F3A]/50 cursor-pointer transition-colors", selected?.id === seg.id ? "bg-[#A855F7]/5" : "hover:bg-[#1A1F2E]")}>
                    <td className="px-4 py-3 text-[#F8FAFC] font-medium">{seg.name}</td>
                    <td className="px-4 py-3 text-right font-mono text-[#F8FAFC]">{seg.revenue}</td>
                    <td className={cn("px-4 py-3 text-right font-mono", seg.growthDirection === "up" ? "text-emerald-400" : seg.growthDirection === "down" ? "text-red-400" : "text-slate-400")}>{seg.growth}</td>
                    <td className="px-4 py-3 text-right font-mono text-[#94A3B8]">{seg.confidence}%</td>
                    <td className="px-4 py-3 text-right font-mono text-[#94A3B8]">{seg.signalCount}</td>
                    <td className="px-4 py-3 text-center"><PriorityBadge priority={seg.priority} /></td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-sm text-[#64748B]">No segments match the selected type.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Segment Detail */}
        <div className="col-span-4 space-y-4">
          {selected && (
            <>
              <div className="card p-4">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-3">Segment Detail</h3>
                <h2 className="text-lg font-semibold mb-3">{selected.name}</h2>
                <div className="space-y-3">
                  {[{ label: "Revenue", value: selected.revenue }, { label: "Growth", value: selected.growth }, { label: "Signals", value: String(selected.signalCount) }].map(({ label, value }) => (
                    <div key={label} className="flex items-center justify-between py-1.5 border-b border-[#2A2F3A] last:border-0">
                      <span className="text-xs text-[#64748B]">{label}</span>
                      <span className="text-sm font-mono text-[#F8FAFC]">{value}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-4">
                  <div className="text-[10px] font-mono text-[#64748B] mb-1.5 uppercase">Confidence</div>
                  <VisualConfidence score={selected.confidence} />
                </div>
              </div>

              <div className="card p-4">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-3">AI Narrative</h3>
                <p className="text-xs text-[#94A3B8] leading-relaxed">
                  {selected.name} segment shows {selected.growthDirection === "up" ? "positive momentum" : selected.growthDirection === "down" ? "declining trajectory" : "stable performance"} with {selected.growth} growth over the current data window.
                  {selected.signalCount > 0 ? ` ${selected.signalCount} active signal(s) detected requiring attention.` : " No active anomalies detected."}
                  {" "}Structural confidence at {selected.confidence}% based on deterministic analysis.
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}

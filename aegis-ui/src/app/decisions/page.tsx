"use client";

import { AppShell } from "@/components/layout/AppShell";
import { DecisionCard } from "@/components/decisions/DecisionCard";
import { mockDecisions } from "@/lib/mockData";
import { useAegisStore } from "@/store/aegisStore";
import { cn } from "@/lib/utils";
import { useState } from "react";

const filters = ["All", "Critical", "High", "Medium", "Resolved"];

// Deterministic heatmap (no Math.random — prevents hydration mismatch)
function seededHeat(i: number) { return ((Math.sin(i * 1337 + 42) % 1) + 1) % 1; }

export default function DecisionsPage() {
  const [activeFilter, setActiveFilter] = useState("All");
  const { decisions: liveDecisions, rawAnalysis } = useAegisStore();
  const hasData = rawAnalysis !== null && liveDecisions.length > 0;
  const decisions = hasData ? liveDecisions : mockDecisions;

  const filtered = activeFilter === "All" ? decisions : activeFilter === "Resolved" ? decisions.filter((d) => d.status === "resolved") : decisions.filter((d) => d.priority === activeFilter.toUpperCase());

  return (
    <AppShell>
      <div className="grid grid-cols-12 gap-6 h-full">
        <div className="col-span-8 space-y-6 overflow-y-auto">
          <div>
            <h1 className="text-xl font-semibold mb-1">Decision Feed</h1>
            <p className="text-sm text-[#64748B]">Live anomaly timeline with root cause analysis and strategic recommendations.</p>
          </div>

          <div className="flex items-center gap-2">
            {filters.map((f) => (
              <button key={f} onClick={() => setActiveFilter(f)} className={cn("px-3 py-1.5 text-[11px] font-mono rounded transition-all", activeFilter === f ? "bg-[#A855F7]/10 text-[#A855F7] border border-[#A855F7]/30" : "text-[#64748B] border border-[#2A2F3A] hover:text-[#94A3B8] hover:border-[#3A4150]")}>
                {f}
              </button>
            ))}
            {hasData && (
              <span className="ml-auto text-[9px] font-mono text-emerald-400 border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 rounded">LIVE DATA</span>
            )}
          </div>

          <div className="space-y-3 stagger-children">
            {filtered.map((d) => (
              <DecisionCard key={d.id} decision={d} />
            ))}
            {filtered.length === 0 && (
              <div className="card p-8 text-center text-sm text-[#64748B]">
                No decisions match the selected filter.
              </div>
            )}
          </div>
        </div>

        <div className="col-span-4 space-y-4">
          {/* Signal Severity Map */}
          <div className="card p-4">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-3">Signal Severity Map</h3>
            <div className="grid grid-cols-7 gap-1">
              {Array.from({ length: 35 }).map((_, i) => {
                const intensity = seededHeat(i);
                return <div key={i} className={cn("aspect-square rounded-sm", intensity > 0.7 ? "bg-red-500/60" : intensity > 0.4 ? "bg-amber-500/40" : intensity > 0.15 ? "bg-emerald-500/30" : "bg-[#1A1F2E]")} />;
              })}
            </div>
            <div className="flex items-center justify-between mt-2 text-[9px] font-mono text-[#64748B]">
              <span>Low</span><span>High</span>
            </div>
          </div>

          {/* Action Queue */}
          <div className="card p-4">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-3">Action Queue</h3>
            <div className="space-y-2">
              {[
                { label: "Pending", count: decisions.filter((d) => d.status === "pending").length, color: "text-amber-400" },
                { label: "Critical", count: decisions.filter((d) => d.priority === "CRITICAL").length, color: "text-red-400" },
                { label: "Acknowledged", count: decisions.filter((d) => d.status === "acknowledged").length, color: "text-blue-400" },
                { label: "Resolved", count: decisions.filter((d) => d.status === "resolved").length, color: "text-emerald-400" },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between py-1.5 border-b border-[#2A2F3A] last:border-0">
                  <span className="text-xs text-[#94A3B8]">{item.label}</span>
                  <span className={cn("text-sm font-mono font-medium", item.color)}>{item.count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

"use client";

import { cn } from "@/lib/utils";
import { VisualConfidence } from "@/components/ui/VisualConfidence";
import type { SystemState } from "@/lib/types";

const stateConfig: Record<SystemState, { label: string; color: string }> = {
  ACTIONABLE: { label: "ACTIONABLE", color: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10" },
  MIXED: { label: "MIXED", color: "text-amber-400 border-amber-500/30 bg-amber-500/10" },
  NO_SIGNAL: { label: "NO SIGNAL", color: "text-slate-400 border-slate-500/30 bg-slate-500/10" },
  DATA_ISSUE: { label: "DATA ISSUE", color: "text-red-400 border-red-500/30 bg-red-500/10" },
  STABLE: { label: "STABLE", color: "text-blue-400 border-blue-500/30 bg-blue-500/10" },
};

export function DecisionHeader({ state, headline, confidence }: { state: SystemState; headline: string; confidence: number }) {
  const config = stateConfig[state];

  return (
    <div className="card p-6 animate-fade-in-up">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-3">
            <span className={cn("inline-flex items-center px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider border", config.color)}>
              {config.label}
            </span>
            <span className="text-[10px] font-mono text-[#64748B]">EXECUTIVE SUMMARY</span>
          </div>
          <h2 className="text-xl font-semibold text-[#F8FAFC] leading-tight">{headline}</h2>
        </div>
        <div className="ml-6 shrink-0">
          <div className="text-[10px] font-mono text-[#64748B] mb-1.5 uppercase">Structural Confidence</div>
          <VisualConfidence score={confidence} />
        </div>
      </div>
    </div>
  );
}

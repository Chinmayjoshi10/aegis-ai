"use client";

import { cn, getRelativeTime } from "@/lib/utils";
import { PriorityBadge } from "@/components/ui/PriorityBadge";
import { VisualConfidence } from "@/components/ui/VisualConfidence";
import type { Decision } from "@/lib/types";
import { ChevronRight } from "lucide-react";

export function DecisionCard({ decision }: { decision: Decision }) {
  const borderColor = {
    CRITICAL: "border-l-red-500",
    HIGH: "border-l-amber-500",
    MEDIUM: "border-l-blue-500",
    LOW: "border-l-slate-500",
  }[decision.priority];

  return (
    <div className={cn("card border-l-[3px] p-4 cursor-pointer group", borderColor)}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <PriorityBadge priority={decision.priority} />
          <span className="text-[10px] font-mono text-[#64748B]">{getRelativeTime(decision.timestamp)}</span>
        </div>
        <ChevronRight className="w-4 h-4 text-[#3A4150] group-hover:text-[#A855F7] transition-colors" />
      </div>
      <h3 className="text-sm font-medium text-[#F8FAFC] mb-2 leading-snug">{decision.headline}</h3>
      <p className="text-xs text-[#64748B] mb-3 line-clamp-2">{decision.description}</p>
      <div className="flex items-center justify-between">
        <VisualConfidence score={decision.confidence} size="sm" />
        <div className="flex items-center gap-1">
          {decision.evidence.slice(0, 2).map((e, i) => (
            <span key={i} className="inline-flex items-center px-1.5 py-0.5 text-[9px] font-mono bg-[#1A1F2E] border border-[#2A2F3A] rounded text-[#94A3B8] max-w-[120px] truncate">
              {e}
            </span>
          ))}
          {decision.evidence.length > 2 && (
            <span className="text-[9px] font-mono text-[#64748B]">+{decision.evidence.length - 2}</span>
          )}
        </div>
      </div>
    </div>
  );
}

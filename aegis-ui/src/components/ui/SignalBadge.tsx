"use client";

import { cn } from "@/lib/utils";
import type { SignalDirection, SignalType } from "@/lib/types";

const directionIcons: Record<SignalDirection, string> = { UP: "↑", DOWN: "↓", FLAT: "→" };
const directionColors: Record<SignalDirection, string> = {
  UP: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  DOWN: "text-red-400 border-red-500/30 bg-red-500/10",
  FLAT: "text-slate-400 border-slate-500/30 bg-slate-500/10",
};

export function SignalBadge({ direction, type }: { direction: SignalDirection; type: SignalType }) {
  return (
    <div className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-mono uppercase tracking-wider", directionColors[direction])}>
      <span className="font-bold">{directionIcons[direction]}</span>
      <span>{type}</span>
    </div>
  );
}

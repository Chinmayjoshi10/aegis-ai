"use client";

import { cn, getConfidenceColor } from "@/lib/utils";

export function VisualConfidence({ score, size = "default" }: { score: number; size?: "sm" | "default" | "lg" }) {
  const blocks = 10;
  const filled = Math.round(score / 10);
  const color = getConfidenceColor(score);
  const glow = score >= 80 ? "shadow-[0_0_6px_rgba(16,185,129,0.4)]" : "";
  const dims = size === "sm" ? "w-1.5 h-3" : size === "lg" ? "w-3 h-6" : "w-2 h-4";
  const textSize = size === "sm" ? "text-[10px]" : size === "lg" ? "text-base" : "text-sm";

  return (
    <div className="flex gap-[3px] items-center">
      {Array.from({ length: blocks }).map((_, i) => (
        <div key={i} className={cn(dims, "rounded-[1px] transition-all duration-300", i < filled ? `${color} ${glow}` : "bg-[#2A2F3A]")} />
      ))}
      <span className={cn("ml-2 font-mono", textSize, "text-[#F8FAFC]")}>{score}%</span>
    </div>
  );
}

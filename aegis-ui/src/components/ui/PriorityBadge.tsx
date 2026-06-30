"use client";

import { cn, getPriorityColor } from "@/lib/utils";
import type { Priority } from "@/lib/types";

export function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider border", getPriorityColor(priority))}>
      {priority}
    </span>
  );
}

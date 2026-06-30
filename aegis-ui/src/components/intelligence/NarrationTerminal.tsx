"use client";

import { useState, useEffect } from "react";
import type { NarrationData } from "@/lib/types";

export function NarrationTerminal({ narration }: { narration: NarrationData }) {
  const [displayed, setDisplayed] = useState("");
  const [cursorVisible, setCursorVisible] = useState(true);

  useEffect(() => {
    let i = 0;
    const interval = setInterval(() => {
      if (i < narration.text.length) {
        setDisplayed(narration.text.slice(0, i + 1));
        i++;
      } else {
        clearInterval(interval);
      }
    }, 18);
    return () => clearInterval(interval);
  }, [narration.text]);

  useEffect(() => {
    const cursor = setInterval(() => setCursorVisible((v) => !v), 500);
    return () => clearInterval(cursor);
  }, []);

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8]">Intelligence Briefing</h3>
        <div className="flex items-center gap-2">
          <span className="text-[9px] font-mono text-emerald-400 border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 rounded">
            {narration.mode}
          </span>
          {narration.grounded && (
            <span className="text-[9px] font-mono text-blue-400 border border-blue-500/30 bg-blue-500/10 px-1.5 py-0.5 rounded">
              GROUNDED
            </span>
          )}
        </div>
      </div>
      <div className="font-mono text-xs text-[#94A3B8] leading-relaxed whitespace-pre-wrap">
        {displayed}
        <span className={`inline-block w-[6px] h-[14px] bg-[#A855F7] ml-0.5 align-middle transition-opacity ${cursorVisible ? "opacity-100" : "opacity-0"}`} />
      </div>
    </div>
  );
}

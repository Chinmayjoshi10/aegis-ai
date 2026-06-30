"use client";

import { cn } from "@/lib/utils";
import { useAegisStore } from "@/store/aegisStore";
import type { TimeRange } from "@/lib/types";
import { useState, useEffect } from "react";
import { Key, X, Wifi, WifiOff } from "lucide-react";

const ranges: TimeRange[] = ["7D", "30D", "90D", "YTD"];

export function GlobalHeader() {
  const timeRange = useAegisStore((s) => s.timeRange);
  const setTimeRange = useAegisStore((s) => s.setTimeRange);
  const systemMode = useAegisStore((s) => s.systemMode);
  const apiKey = useAegisStore((s) => s.apiKey);
  const setApiKey = useAegisStore((s) => s.setApiKey);
  const backendOnline = useAegisStore((s) => s.backendOnline);
  const llmAvailable = useAegisStore((s) => s.llmAvailable);

  const [showKeyModal, setShowKeyModal] = useState(false);
  const [keyInput, setKeyInput] = useState("");

  // Hydrate API key from localStorage on mount (client-side only)
  useEffect(() => {
    const stored = localStorage.getItem("aegis_api_key") || "";
    if (stored && !apiKey) {
      setApiKey(stored);
    }
    setKeyInput(stored || apiKey);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSaveKey = () => {
    setApiKey(keyInput);
    setShowKeyModal(false);
  };

  return (
    <>
      <header className="h-14 flex items-center justify-between px-6 bg-[#05070D] border-b border-[#2A2F3A] shrink-0">
        <div className="flex items-center gap-4">
          <h1 className="text-sm font-semibold tracking-[0.15em] text-[#F8FAFC]">COMMAND CENTER</h1>
          <div className={cn(
            "px-2 py-0.5 text-[10px] border rounded font-mono",
            systemMode === "DETERMINISTIC"
              ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/10"
              : "border-[#A855F7]/30 text-[#A855F7] bg-[#A855F7]/10"
          )}>
            {systemMode === "DETERMINISTIC" ? "DETERMINISTIC" : "LLM AUGMENTED"}
          </div>
          {/* Backend status */}
          <div className="flex items-center gap-1.5">
            {backendOnline ? (
              <Wifi className="w-3 h-3 text-emerald-500" />
            ) : (
              <WifiOff className="w-3 h-3 text-red-400" />
            )}
            <span className={cn("text-[9px] font-mono", backendOnline ? "text-emerald-400" : "text-red-400")}>
              {backendOnline ? "CONNECTED" : "OFFLINE"}
            </span>
          </div>
          {llmAvailable && (
            <div className="px-2 py-0.5 text-[9px] border border-blue-500/30 text-blue-400 bg-blue-500/10 rounded font-mono">
              GEMMA ACTIVE
            </div>
          )}
        </div>

        <div className="flex items-center gap-6">
          <button
            onClick={() => setShowKeyModal(true)}
            className="flex items-center gap-1.5 text-[10px] font-mono text-[#64748B] hover:text-[#94A3B8] transition-colors"
          >
            <Key className="w-3 h-3" />
            {apiKey ? "Key: ••••" + apiKey.slice(-4) : "Set API Key"}
          </button>

          <div className="text-[10px] font-mono text-[#64748B] text-right leading-relaxed">
            <p>Last Updated: 2 mins ago</p>
            <p>Data Window: {timeRange}</p>
          </div>

          {/* Time Range Selector */}
          <div className="flex p-1 bg-[#05070D] border border-[#2A2F3A] rounded">
            {ranges.map((r) => (
              <button
                key={r}
                onClick={() => setTimeRange(r)}
                className={cn(
                  "px-3 py-1 text-[11px] font-mono transition-all duration-200 rounded-sm",
                  timeRange === r
                    ? "bg-[#2A2F3A] text-[#F8FAFC]"
                    : "text-[#64748B] hover:text-[#94A3B8]"
                )}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* API Key Modal */}
      {showKeyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-[#0E111A] border border-[#2A2F3A] rounded-lg p-6 w-[420px] shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold">Configure API Key</h2>
              <button onClick={() => setShowKeyModal(false)} className="text-[#64748B] hover:text-[#F8FAFC]"><X className="w-4 h-4" /></button>
            </div>
            <p className="text-xs text-[#64748B] mb-4">Enter your AEGIS API key to connect to the backend intelligence engine.</p>
            <input
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="f4ccaadbeab547f61f3d..."
              className="w-full bg-[#05070D] border border-[#2A2F3A] rounded px-3 py-2.5 text-sm font-mono text-[#F8FAFC] placeholder:text-[#334155] outline-none focus:border-[#A855F7] transition-colors mb-4"
            />
            <div className="flex gap-3">
              <button onClick={handleSaveKey} className="flex-1 py-2.5 bg-[#A855F7] text-white text-sm font-medium rounded hover:bg-[#9333EA] transition-colors">
                Save Key
              </button>
              <button onClick={() => setShowKeyModal(false)} className="flex-1 py-2.5 border border-[#2A2F3A] text-[#94A3B8] text-sm rounded hover:border-[#3A4150] transition-colors">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

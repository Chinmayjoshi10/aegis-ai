"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { useAegisStore } from "@/store/aegisStore";
import type { ChatMessage } from "@/lib/types";
import { Send, Loader2 } from "lucide-react";

function ChatCitation({ label, targetId }: { label: string; targetId: string }) {
  const { setFocus } = useAegisStore();
  return (
    <span
      onMouseEnter={() => setFocus(targetId)}
      onMouseLeave={() => setFocus(null)}
      className="inline-flex items-center px-1.5 py-0.5 ml-1 text-[10px] font-mono border border-[#A855F7]/50 text-[#A855F7] rounded cursor-pointer hover:bg-[#A855F7] hover:text-white transition-colors"
    >
      {label}
    </span>
  );
}

interface ChatInterfaceProps {
  messages: ChatMessage[];
  onSend?: (message: string) => void;
  loading?: boolean;
}

export function ChatInterface({ messages, onSend, loading = false }: ChatInterfaceProps) {
  const [input, setInput] = useState("");
  const [localMessages, setLocalMessages] = useState<ChatMessage[]>([]);

  const displayMessages = onSend ? messages : [...messages, ...localMessages];

  const handleSend = () => {
    if (!input.trim() || loading) return;

    if (onSend) {
      onSend(input);
    } else {
      // Local-only fallback
      const userMsg: ChatMessage = {
        id: `msg-${Date.now()}`,
        role: "user",
        content: input,
        timestamp: new Date().toISOString(),
      };
      const assistantMsg: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        role: "assistant",
        content: "Connect to the AEGIS backend to enable live intelligence queries. Start the FastAPI server and upload a dataset first.",
        confidence: 0,
        timestamp: new Date().toISOString(),
      };
      setLocalMessages((prev) => [...prev, userMsg, assistantMsg]);
    }
    setInput("");
  };

  return (
    <div className="card flex flex-col h-[320px]">
      <div className="px-4 py-3 border-b border-[#2A2F3A] flex items-center justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8]">AEGIS Analyst</h3>
        <div className="flex items-center gap-1.5">
          <div className={cn("w-2 h-2 rounded-full", onSend ? "bg-emerald-500" : "bg-amber-500")} />
          <span className="text-[9px] font-mono text-[#64748B]">{onSend ? "LIVE" : "DEMO"}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {displayMessages.map((msg) => (
          <div key={msg.id} className={cn("flex flex-col", msg.role === "user" ? "items-end" : "items-start")}>
            <div className={cn(
              "max-w-[90%] rounded px-3 py-2 text-xs leading-relaxed",
              msg.role === "user"
                ? "bg-[#A855F7]/10 border border-[#A855F7]/30 text-[#F8FAFC]"
                : "bg-[#1A1F2E] border border-[#2A2F3A] text-[#94A3B8]"
            )}>
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {msg.citations && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {msg.citations.map((c) => (
                    <ChatCitation key={c.id} label={c.label} targetId={c.targetId} />
                  ))}
                </div>
              )}
              {msg.confidence !== undefined && msg.confidence > 0 && (
                <div className="mt-2 text-[9px] font-mono text-[#64748B]">Confidence: {msg.confidence}%</div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex flex-col items-start">
            <div className="max-w-[90%] rounded px-3 py-2 text-xs leading-relaxed bg-[#1A1F2E] border border-[#2A2F3A] text-[#94A3B8] inline-flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-[#A855F7]" />
              <span>AEGIS is reasoning over the structured analysis…</span>
            </div>
          </div>
        )}
      </div>

      <div className="p-3 border-t border-[#2A2F3A]">
        <div className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder={loading ? "Waiting for AEGIS…" : "Ask AEGIS anything..."}
            disabled={loading}
            className="flex-1 bg-[#05070D] border border-[#2A2F3A] rounded px-3 py-2 text-xs text-[#F8FAFC] placeholder:text-[#334155] outline-none focus:border-[#A855F7] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            aria-busy={loading}
            className="p-2 bg-[#A855F7]/10 border border-[#A855F7]/30 rounded hover:bg-[#A855F7]/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 text-[#A855F7] animate-spin" /> : <Send className="w-3.5 h-3.5 text-[#A855F7]" />}
          </button>
        </div>
      </div>
    </div>
  );
}

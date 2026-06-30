"use client";

import { useEffect, useRef } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ChatInterface } from "@/components/intelligence/ChatInterface";
import { VisualConfidence } from "@/components/ui/VisualConfidence";
import { TrendChart } from "@/components/charts/TrendChart";
import { useAegisStore } from "@/store/aegisStore";
import { useChat } from "@/hooks/useChat";
import { checkLLMHealth } from "@/services/apiClient";
import { mockChatMessages, mockChartData } from "@/lib/mockData";

const suggestedQuestions = [
  "What is the current system state?",
  "Which signals were detected?",
  "What actions should we take?",
  "What is the data quality status?",
  "What drove the cost changes?",
];

export default function AnalystPage() {
  const { rawAnalysis, chartData, kpis } = useAegisStore();
  const { messages, sendMessage, loading, warmup } = useChat();
  const hasData = rawAnalysis !== null;

  // Pre-warm the local LLM once when the analyst page is first opened with
  // data loaded. The first chat would otherwise pay a 90-180s cold-load.
  // Fire-and-forget; warmup is idempotent and cheap if already loaded.
  const warmedRef = useRef(false);
  useEffect(() => {
    if (!hasData || warmedRef.current) return;
    warmedRef.current = true;
    (async () => {
      try {
        const h = await checkLLMHealth();
        if (h.available && !h.model_loaded) {
          void warmup();
        }
      } catch {
        // Health probe failures are non-fatal — the chat send path will surface a real error.
      }
    })();
  }, [hasData, warmup]);

  const displayMessages = messages.length > 0 ? messages : mockChatMessages;
  const displayChartData = hasData ? chartData : mockChartData;

  // Get top 3 signals for evidence panel
  const topSignals = hasData && rawAnalysis?.company_insights
    ? (rawAnalysis.company_insights as Array<Record<string, unknown>>)
        .filter((i) => i.type === "SIGNAL")
        .slice(0, 3)
        .map((s) => ({
          label: `${s.metric}: ${s.direction || s.validated_direction}`,
          conf: Math.round(Number(s.confidence || 0) * 100),
        }))
    : [
        { label: "Bias signal: DOWNWARD", conf: 78 },
        { label: "Segment: Tier 1 Channels", conf: 82 },
        { label: "Cross-metric: Revenue uncorrelated", conf: 71 },
      ];

  return (
    <AppShell>
      <div className="grid grid-cols-12 gap-6 h-full">
        <div className="col-span-7 flex flex-col h-full">
          <div className="mb-4">
            <h1 className="text-xl font-semibold mb-1">AEGIS Analyst</h1>
            <p className="text-sm text-[#64748B]">
              {hasData
                ? "Connected to live analysis. Ask questions grounded in deterministic intelligence."
                : "Upload data to enable grounded intelligence. Currently in demo mode."}
            </p>
          </div>

          <div className="flex-1 min-h-0">
            <div className="h-full">
              <ChatInterface
                messages={displayMessages}
                onSend={hasData ? sendMessage : undefined}
                loading={loading}
              />
            </div>
          </div>

          <div className="mt-4">
            <p className="text-[10px] font-mono text-[#64748B] mb-2 uppercase">Suggested Questions</p>
            <div className="flex flex-wrap gap-2">
              {suggestedQuestions.map((q) => (
                <button
                  key={q}
                  onClick={() => hasData && !loading && sendMessage(q)}
                  className="px-3 py-1.5 text-[11px] text-[#94A3B8] border border-[#2A2F3A] rounded hover:border-[#A855F7]/30 hover:text-[#A855F7] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={!hasData || loading}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Evidence Panel */}
        <div className="col-span-5 space-y-4 overflow-y-auto">
          <div className="card p-4">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-3">Referenced Data</h3>
            {displayChartData.length > 0 && (
              <TrendChart
                title={hasData ? Object.keys(displayChartData[0]).filter((k) => k !== "day")[0]?.replace(/_/g, " ") || "Metric" : "Cost Trend"}
                data={displayChartData}
                dataKey={hasData ? Object.keys(displayChartData[0]).filter((k) => k !== "day")[0] || "" : "cost"}
                color="#EF4444"
              />
            )}
          </div>

          <div className="card p-4">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-3">Evidence</h3>
            <div className="space-y-2">
              {topSignals.map((e, i) => (
                <div key={i} className="flex items-center justify-between py-2 border-b border-[#2A2F3A] last:border-0">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center justify-center w-5 h-5 text-[10px] font-mono border border-[#A855F7]/50 text-[#A855F7] rounded">{i + 1}</span>
                    <span className="text-xs text-[#94A3B8]">{e.label}</span>
                  </div>
                  <VisualConfidence score={e.conf} size="sm" />
                </div>
              ))}
            </div>
          </div>

          <div className="card p-4">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-3">Follow-Up</h3>
            <div className="space-y-1.5">
              {["Show segment breakdown", "What's the forecast?", "Compare to last year"].map((q) => (
                <button
                  key={q}
                  onClick={() => hasData && !loading && sendMessage(q)}
                  disabled={!hasData || loading}
                  className="w-full text-left px-3 py-2 text-xs text-[#94A3B8] border border-[#2A2F3A] rounded hover:border-[#A855F7]/30 hover:text-[#A855F7] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

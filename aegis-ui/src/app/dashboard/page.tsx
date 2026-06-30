"use client";

import { useEffect, useRef } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { DecisionHeader } from "@/components/decisions/DecisionHeader";
import { KpiGrid } from "@/components/kpi/KpiCard";
import { TrendChart } from "@/components/charts/TrendChart";
import { DecisionCard } from "@/components/decisions/DecisionCard";
import { NarrationTerminal } from "@/components/intelligence/NarrationTerminal";
import { ChatInterface } from "@/components/intelligence/ChatInterface";
import { UploadWorkflow } from "@/components/upload/UploadWorkflow";
import { useAegisStore } from "@/store/aegisStore";
import { useAnalysis } from "@/hooks/useAnalysis";
import { useChat } from "@/hooks/useChat";
import { transformSystemState } from "@/services/dataTransformer";
import { mockKpis, mockDecisions, mockNarration, mockChartData, mockChatMessages } from "@/lib/mockData";
import { Upload } from "lucide-react";

export default function DashboardPage() {
  // Use individual selectors — prevents re-render cascade
  const rawAnalysis = useAegisStore((s) => s.rawAnalysis);
  const setRawAnalysis = useAegisStore((s) => s.setRawAnalysis);
  const kpis = useAegisStore((s) => s.kpis);
  const decisions = useAegisStore((s) => s.decisions);
  const narration = useAegisStore((s) => s.narration);
  const chartData = useAegisStore((s) => s.chartData);
  const headline = useAegisStore((s) => s.headline);
  const confidence = useAegisStore((s) => s.confidence);
  const backendOnline = useAegisStore((s) => s.backendOnline);

  const { checkBackend, hasData } = useAnalysis();
  const { messages, sendMessage } = useChat();

  // Check backend health on mount — use ref to prevent re-creating interval
  const healthCheckStarted = useRef(false);
  useEffect(() => {
    if (healthCheckStarted.current) return;
    healthCheckStarted.current = true;
    checkBackend();
    const interval = setInterval(checkBackend, 30000);
    return () => clearInterval(interval);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleNewUpload = () => {
    setRawAnalysis(null);
    useAegisStore.setState({ segments: [], kpis: [], decisions: [], chartData: [], narration: null });
  };

  // Use live data if available, otherwise fallback to mock
  const displayKpis = hasData ? kpis : mockKpis;
  const displayDecisions = hasData ? decisions : mockDecisions;
  const displayNarration = hasData && narration ? narration : mockNarration;
  const displayChartData = hasData ? chartData : mockChartData;
  const displayHeadline = hasData ? headline : "Cost Efficiency Improving Across Tier 1 Channels — Enterprise Revenue Trajectory Confirmed";
  const displayConfidence = hasData ? confidence : 82;
  const displayState = hasData && rawAnalysis ? transformSystemState(rawAnalysis.system_state) : "ACTIONABLE";
  const chatMessages = messages.length > 0 ? messages : mockChatMessages;

  // Get valid chart metric keys
  const chartMetrics = hasData && displayChartData.length > 0
    ? Object.keys(displayChartData[0]).filter((k) => k !== "day").slice(0, 4)
    : ["revenue", "cost", "conversion", "cac"];

  const chartColors = ["#F8FAFC", "#EF4444", "#10B981", "#F59E0B"];

  return (
    <AppShell>
      <div className="grid grid-cols-12 gap-6 h-full">
        {/* Main Content — 9 columns */}
        <div className="col-span-9 space-y-6 overflow-y-auto pr-2">
          {/* Backend status + new upload button */}
          <div className="flex items-center justify-between gap-3">
            {!backendOnline && (
              <div className="flex items-center gap-2 px-3 py-2 text-[10px] font-mono border border-amber-500/30 bg-amber-500/5 text-amber-400 rounded flex-1">
                <div className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                Backend offline — displaying demo data. Start the FastAPI server to enable live analysis.
              </div>
            )}
            {backendOnline && !hasData && <div className="flex-1" />}
            {hasData && (
              <button
                onClick={handleNewUpload}
                className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-mono border border-[#2A2F3A] text-[#94A3B8] rounded hover:border-[#A855F7]/50 hover:text-[#A855F7] transition-colors ml-auto"
              >
                <Upload className="w-3 h-3" />
                Analyse New CSV
              </button>
            )}
          </div>

          {/* Upload zone — always visible when no data */}
          {!hasData && (
            <UploadWorkflow />
          )}

          {/* Decision Header */}
          <DecisionHeader
            state={displayState}
            headline={displayHeadline}
            confidence={displayConfidence}
          />

          {/* KPI Grid */}
          <KpiGrid kpis={displayKpis} />

          {/* Chart Grid */}
          <div className="grid grid-cols-2 gap-4">
            {chartMetrics.map((metric, i) => (
              <TrendChart
                key={metric}
                title={metric.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase()) + " Trend"}
                data={displayChartData}
                dataKey={metric}
                color={chartColors[i % chartColors.length]}
              />
            ))}
          </div>

          {/* Decision Feed */}
          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-4">Active Decisions</h2>
            <div className="space-y-3 stagger-children">
              {displayDecisions.map((d) => (
                <DecisionCard key={d.id} decision={d} />
              ))}
            </div>
          </div>
        </div>

        {/* Intelligence Panel — 3 columns */}
        <div className="col-span-3 space-y-4 overflow-y-auto">
          <NarrationTerminal narration={displayNarration} />
          <ChatInterface messages={chatMessages} onSend={sendMessage} />
        </div>
      </div>
    </AppShell>
  );
}

/** AEGIS Data Transformer — converts raw API responses into frontend-ready shapes.
 *
 * This layer acts as a firewall between the backend JSON schema and the UI types.
 * If the backend changes structure, ONLY this file needs updating.
 */

import type { KpiData, Decision, Priority, Signal, SignalDirection, SignalType, Segment, NarrationData, SystemState } from "@/lib/types";
import type { AnalyzeResponse } from "./apiClient";

// ─── System State ──────────────────────────────
export function transformSystemState(raw: string): SystemState {
  const map: Record<string, SystemState> = {
    INSIGHTFUL: "ACTIONABLE",
    SILENT: "NO_SIGNAL",
    OBSERVATION: "STABLE",
    DATA_ISSUE: "DATA_ISSUE",
  };
  return map[raw] || "MIXED";
}

// ─── KPIs from reality_snapshot ────────────────
export function transformKpis(response: AnalyzeResponse): KpiData[] {
  const numeric = response.reality_snapshot?.numeric || {};
  const insights = response.company_insights || [];

  return Object.entries(numeric).map(([metric, stats]) => {
    // Find matching signal
    const matchingSignal = insights.find(
      (i) => (i as Record<string, unknown>).metric === metric && (i as Record<string, unknown>).type === "SIGNAL"
    ) as Record<string, unknown> | undefined;

    const mean = stats.mean || 0;
    const isMonetary = metric.toLowerCase().includes("revenue") || metric.toLowerCase().includes("cost") || metric.toLowerCase().includes("price") || metric.toLowerCase().includes("sales");
    const value = isMonetary
      ? mean >= 1_000_000 ? `$${(mean / 1_000_000).toFixed(1)}M` : mean >= 1_000 ? `$${(mean / 1_000).toFixed(0)}K` : `$${mean.toFixed(0)}`
      : metric.toLowerCase().includes("rate") || metric.toLowerCase().includes("conversion")
        ? `${mean.toFixed(1)}%`
        : mean.toFixed(1);

    let signal: Signal | undefined;
    if (matchingSignal) {
      const dir = String(matchingSignal.direction || matchingSignal.validated_direction || "FLAT");
      signal = {
        id: `sig-${metric}`,
        direction: (dir === "UPWARD" ? "UP" : dir === "DOWNWARD" ? "DOWN" : "FLAT") as SignalDirection,
        type: (String(matchingSignal.primitive || matchingSignal.subtype || "TREND").toUpperCase()) as SignalType,
        metric,
        magnitude: Number(matchingSignal.magnitude_pct || matchingSignal.magnitude || 0),
        confidence: Number(matchingSignal.confidence || 0) * 100,
      };
    }

    // Calculate delta from drift report
    const drift = (response.drift_report as Record<string, Record<string, Record<string, unknown>>>)?.numeric?.[metric];
    let delta = "0%";
    let deltaDirection: "up" | "down" | "flat" = "flat";
    if (drift && typeof drift.baseline_mean === "number" && drift.baseline_mean !== 0) {
      const pctChange = ((mean - (drift.baseline_mean as number)) / Math.abs(drift.baseline_mean as number)) * 100;
      delta = `${pctChange >= 0 ? "+" : ""}${pctChange.toFixed(1)}%`;
      deltaDirection = pctChange > 0.5 ? "up" : pctChange < -0.5 ? "down" : "flat";
    }

    return {
      id: `kpi-${metric}`,
      metric: metric.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase()),
      value,
      delta,
      deltaDirection,
      signal,
    };
  });
}

// ─── Decisions ─────────────────────────────────
export function transformDecisions(response: AnalyzeResponse): Decision[] {
  const finals = response.final_decisions || [];

  return finals.map((d, i) => ({
    id: `dec-${i}`,
    headline: d.title || "Untitled Decision",
    description: d.summary || "",
    priority: (d.priority || "MEDIUM") as Priority,
    confidence: Math.round((d.confidence || 0) * 100),
    rootCause: d.summary,
    action: d.action || undefined,
    evidence: d.signals || [],
    timestamp: new Date().toISOString(),
    status: "pending" as const,
  }));
}

// ─── Segments ──────────────────────────────────
// Backend shape: { "Dimension=Value": [{ type, metric, deviation, segment_mean, global_mean, dimension, segment_value, ... }] }
export function transformSegments(response: AnalyzeResponse): Segment[] {
  const segDecisions = response.segment_decisions || {};
  const segments: Segment[] = [];

  Object.entries(segDecisions).forEach(([label, contexts]) => {
    // Each key is "Dimension=Value", e.g. "Campaign_Name=Google_Ads_Q1"
    if (!Array.isArray(contexts) || contexts.length === 0) return;

    const ctxList = contexts as Array<Record<string, unknown>>;
    const first = ctxList[0];

    // Extract dimension and segment name from the label or context fields
    const dimension = (first.dimension as string) || label.split("=")[0] || "Unknown";
    const segmentValue = (first.segment_value as string) || label.split("=").slice(1).join("=") || label;

    // Aggregate across all metric contexts for this segment
    const avgDeviation = ctxList.reduce((sum, c) => sum + (typeof c.deviation === "number" ? c.deviation : 0), 0) / ctxList.length;
    const maxAbsDeviation = Math.max(...ctxList.map(c => Math.abs(typeof c.deviation === "number" ? c.deviation : 0)));

    // Revenue: use the first context's segment_mean as a representative value
    const segMean = typeof first.segment_mean === "number" ? first.segment_mean : 0;
    const revenue = segMean >= 1_000_000
      ? `$${(segMean / 1_000_000).toFixed(1)}M`
      : segMean >= 1_000
        ? `$${(segMean / 1_000).toFixed(0)}K`
        : segMean > 0
          ? `$${segMean.toFixed(0)}`
          : "N/A";

    // Growth: use the average deviation as a percentage
    const growthPct = avgDeviation * 100;
    const growth = `${growthPct >= 0 ? "+" : ""}${growthPct.toFixed(1)}%`;
    const growthDirection: "up" | "down" | "flat" = avgDeviation > 0.01 ? "up" : avgDeviation < -0.01 ? "down" : "flat";

    // Confidence: derive from segment row count share (higher share = higher confidence)
    const segRows = typeof first.segment_rows === "number" ? first.segment_rows : 0;
    const confidence = Math.min(95, Math.max(30, Math.round(50 + segRows * 0.3)));

    // Priority: based on maximum absolute deviation
    const priority: Priority = maxAbsDeviation >= 0.2 ? "HIGH" : maxAbsDeviation >= 0.1 ? "MEDIUM" : "LOW";

    // Format dimension name for type field
    const dimType = dimension
      .replace(/_/g, " ")
      .replace(/\b\w/g, (l: string) => l.toUpperCase());

    segments.push({
      id: `seg-${label}`,
      name: segmentValue,
      type: dimType,
      revenue,
      growth,
      growthDirection,
      confidence,
      signalCount: ctxList.length,
      priority,
    });
  });

  // Sort by priority (HIGH first), then by abs(deviation)
  const priorityOrder: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
  segments.sort((a, b) => (priorityOrder[a.priority] ?? 3) - (priorityOrder[b.priority] ?? 3));

  return segments;
}

// ─── Narration ─────────────────────────────────
export function transformNarration(response: AnalyzeResponse): NarrationData {
  return {
    text: response.narration || response.narrative || "No intelligence briefing available for this analysis.",
    mode: response.narration_meta?.mode === "llm" ? "LLM_AUGMENTED" : "DETERMINISTIC",
    grounded: true,
    timestamp: new Date().toISOString(),
  };
}

// ─── Chart data from reality_snapshot ──────────
export function transformChartData(response: AnalyzeResponse): Array<Record<string, unknown>> {
  const numeric = response.reality_snapshot?.numeric || {};
  const metrics = Object.keys(numeric);
  if (metrics.length === 0) return [];

  // Generate synthetic time series from the stats (for now, until event store time series API exists)
  return Array.from({ length: 30 }, (_, i) => {
    const point: Record<string, unknown> = { day: `Day ${i + 1}` };
    metrics.forEach((m) => {
      const stat = numeric[m];
      if (stat) {
        const mean = stat.mean || 0;
        const std = stat.std || mean * 0.05;
        point[m] = mean + Math.sin(i * 0.3) * std * 0.5 + (Math.random() - 0.5) * std * 0.3;
      }
    });
    return point;
  });
}

// ─── Decision headline from structured analysis ──
export function extractHeadline(response: AnalyzeResponse): string {
  if (response.final_decisions?.length) {
    return response.final_decisions[0].title;
  }
  if (response.narrative) {
    return response.narrative.split(".")[0] + ".";
  }
  return "No significant structural changes detected in the current data window.";
}

// ─── Aggregate confidence ──────────────────────
export function extractConfidence(response: AnalyzeResponse): number {
  const confidences = (response.final_decisions || []).map((d) => d.confidence || 0);
  if (confidences.length === 0) return 0;
  return Math.round((confidences.reduce((a, b) => a + b, 0) / confidences.length) * 100);
}

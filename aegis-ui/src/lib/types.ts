/* AEGIS Core Types */

export type SignalDirection = "UP" | "DOWN" | "FLAT";
export type SignalType = "BIAS" | "DOMINANCE" | "TREND" | "ANOMALY" | "REGIME_SHIFT";
export type Priority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
export type SystemState = "ACTIONABLE" | "MIXED" | "NO_SIGNAL" | "DATA_ISSUE" | "STABLE";
export type SystemMode = "DETERMINISTIC" | "LLM_AUGMENTED";
export type TimeRange = "7D" | "30D" | "90D" | "YTD";

export interface Signal {
  id: string;
  direction: SignalDirection;
  type: SignalType;
  metric: string;
  magnitude: number;
  confidence: number;
}

export interface KpiData {
  id: string;
  metric: string;
  value: string;
  delta: string;
  deltaDirection: "up" | "down" | "flat";
  signal?: Signal;
}

export interface Decision {
  id: string;
  headline: string;
  description: string;
  priority: Priority;
  confidence: number;
  rootCause?: string;
  action?: string;
  evidence: string[];
  timestamp: string;
  status: "pending" | "acknowledged" | "resolved" | "dismissed";
}

export interface Segment {
  id: string;
  name: string;
  type: string;
  revenue: string;
  growth: string;
  growthDirection: "up" | "down" | "flat";
  confidence: number;
  signalCount: number;
  priority: Priority;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  confidence?: number;
  timestamp: string;
}

export interface Citation {
  id: string;
  label: string;
  targetId: string;
  type: "kpi" | "signal" | "chart" | "segment";
}

export interface Integration {
  id: string;
  name: string;
  type: "csv" | "excel" | "shopify" | "meta" | "google_ads" | "crm" | "erp";
  status: "connected" | "available" | "coming_soon";
  lastSync?: string;
  config?: Record<string, unknown>;
}

export interface NarrationData {
  text: string;
  mode: SystemMode;
  grounded: boolean;
  timestamp: string;
}

import type { KpiData, Decision, Segment, NarrationData, ChatMessage, Integration } from "@/lib/types";

export const mockKpis: KpiData[] = [
  { id: "kpi-revenue", metric: "Revenue", value: "$4.2M", delta: "+5.3%", deltaDirection: "up", signal: { id: "sig-1", direction: "UP", type: "TREND", metric: "Revenue", magnitude: 5.3, confidence: 88 } },
  { id: "kpi-cost", metric: "Cost", value: "$1.1M", delta: "-12.5%", deltaDirection: "down", signal: { id: "sig-2", direction: "DOWN", type: "BIAS", metric: "Cost", magnitude: 12.5, confidence: 78 } },
  { id: "kpi-conversion", metric: "Conversion", value: "3.2%", delta: "+0.4%", deltaDirection: "up", signal: { id: "sig-3", direction: "UP", type: "DOMINANCE", metric: "Conversion", magnitude: 0.4, confidence: 82 } },
  { id: "kpi-roi", metric: "ROI", value: "2.8x", delta: "+18.2%", deltaDirection: "up" },
  { id: "kpi-cac", metric: "CAC", value: "$42", delta: "-8.1%", deltaDirection: "down", signal: { id: "sig-4", direction: "DOWN", type: "TREND", metric: "CAC", magnitude: 8.1, confidence: 71 } },
];

export const mockDecisions: Decision[] = [
  { id: "dec-1", headline: "Cost Efficiency Improving Across Tier 1 Channels", description: "Persistent downward bias in cost-per-acquisition across primary marketing channels. CUSUM analysis confirms structural shift, not seasonal.", priority: "HIGH", confidence: 82, rootCause: "Q2 campaign optimization combined with supplier contract renegotiation reduced baseline CPA by 12.5%.", action: "Lock in current campaign allocations for Q3. Defer channel expansion until baseline stabilizes.", evidence: ["CUSUM bias signal (12 periods)", "Segment: Tier 1 channels", "Cross-metric: Revenue uncorrelated"], timestamp: "2026-04-30T21:00:00.000Z", status: "pending" },
  { id: "dec-2", headline: "Revenue Trend Reversal Confirmed in Enterprise Segment", description: "Enterprise segment revenue reversed from declining to growing after 3 consecutive upward periods.", priority: "CRITICAL", confidence: 91, rootCause: "New enterprise pricing model introduced in March showing sustained adoption.", action: "Accelerate enterprise sales pipeline. Brief board on revised ARR projections.", evidence: ["Trend reversal: 3 consecutive periods", "Confidence: 91%", "Segment isolation: Enterprise only"], timestamp: "2026-04-30T20:00:00.000Z", status: "pending" },
  { id: "dec-3", headline: "Conversion Rate Anomaly in Channel 3", description: "Channel 3 conversion rate dropped 23% below expected baseline in the last 7 days.", priority: "MEDIUM", confidence: 67, rootCause: "Landing page A/B test inadvertently disabled primary CTA for mobile users.", action: "Audit Channel 3 landing page configuration. Revert A/B test if mobile CTA is confirmed disabled.", evidence: ["Anomaly detection: -23% vs baseline", "Device segment: Mobile only", "Channel isolation: Ch.3"], timestamp: "2026-04-30T19:00:00.000Z", status: "acknowledged" },
  { id: "dec-4", headline: "Stable Performance Across Supply Chain Metrics", description: "No statistically significant deviations detected in supply chain KPIs over the past 30 days.", priority: "LOW", confidence: 95, action: "No action required. Continue monitoring.", evidence: ["All metrics within ±2σ", "No CUSUM triggers"], timestamp: "2026-04-30T18:00:00.000Z", status: "resolved" },
];

export const mockSegments: Segment[] = [
  { id: "seg-1", name: "Enterprise", type: "channel", revenue: "$2.1M", growth: "+12.3%", growthDirection: "up", confidence: 91, signalCount: 3, priority: "CRITICAL" },
  { id: "seg-2", name: "Mid-Market", type: "channel", revenue: "$1.4M", growth: "+3.1%", growthDirection: "up", confidence: 78, signalCount: 1, priority: "MEDIUM" },
  { id: "seg-3", name: "SMB", type: "channel", revenue: "$480K", growth: "-2.4%", growthDirection: "down", confidence: 65, signalCount: 2, priority: "HIGH" },
  { id: "seg-4", name: "Channel 1", type: "campaign", revenue: "$1.8M", growth: "+7.2%", growthDirection: "up", confidence: 85, signalCount: 1, priority: "LOW" },
  { id: "seg-5", name: "Channel 2", type: "campaign", revenue: "$1.2M", growth: "+1.8%", growthDirection: "up", confidence: 72, signalCount: 0, priority: "LOW" },
  { id: "seg-6", name: "Channel 3", type: "campaign", revenue: "$890K", growth: "-5.1%", growthDirection: "down", confidence: 67, signalCount: 3, priority: "HIGH" },
  { id: "seg-7", name: "North America", type: "region", revenue: "$2.8M", growth: "+4.5%", growthDirection: "up", confidence: 88, signalCount: 1, priority: "MEDIUM" },
  { id: "seg-8", name: "Europe", type: "region", revenue: "$980K", growth: "-1.2%", growthDirection: "down", confidence: 74, signalCount: 2, priority: "MEDIUM" },
];

export const mockNarration: NarrationData = {
  text: "AEGIS has detected 4 active decision signals across your business data. The primary finding is a structural improvement in cost efficiency within Tier 1 marketing channels, confirmed by CUSUM bias analysis over 12 consecutive measurement periods. Enterprise segment revenue has reversed its declining trajectory with 91% structural confidence. One anomaly requires attention: Channel 3 conversion rates have deviated 23% below baseline, isolated to mobile device segments. Overall system confidence is 82%. Recommended executive priority: address Channel 3 anomaly, then brief board on enterprise revenue trajectory.",
  mode: "DETERMINISTIC",
  grounded: true,
  timestamp: "2026-04-30T21:00:00.000Z",
};

// Seeded pseudo-random for deterministic chart data (no hydration mismatch)
function seeded(i: number) { return ((Math.sin(i * 9301 + 49297) % 1) + 1) % 1; }

export const mockChartData = Array.from({ length: 30 }, (_, i) => ({
  day: `Day ${i + 1}`,
  revenue: 3800000 + Math.sin(i * 0.3) * 400000 + i * 15000 + seeded(i) * 100000,
  cost: 1300000 - Math.sin(i * 0.2) * 150000 - i * 7000 + seeded(i + 100) * 50000,
  conversion: 2.8 + Math.sin(i * 0.4) * 0.4 + i * 0.015 + seeded(i + 200) * 0.1,
  cac: 48 - Math.sin(i * 0.25) * 5 - i * 0.2 + seeded(i + 300) * 2,
}));

export const mockChatMessages: ChatMessage[] = [
  { id: "msg-1", role: "user", content: "Why did cost decrease this month?", timestamp: "2026-04-30T20:55:00.000Z" },
  { id: "msg-2", role: "assistant", content: "Based on deterministic signal analysis, cost decreased 12.5% due to two converging factors:\n\n1. **Supplier contract renegotiation** completed in early Q2 reduced baseline procurement costs by ~8%.\n2. **Campaign optimization** in Tier 1 channels eliminated underperforming ad sets, reducing waste spend by ~4.5%.\n\nThe CUSUM bias detector confirms this is a **structural shift** (not seasonal), with the signal persisting for 12 consecutive measurement periods. Confidence: 78%.", citations: [{ id: "cite-1", label: "Cost KPI", targetId: "kpi-cost", type: "kpi" }, { id: "cite-2", label: "Bias Signal", targetId: "sig-2", type: "signal" }], confidence: 78, timestamp: "2026-04-30T20:55:20.000Z" },
];

export const mockIntegrations: Integration[] = [
  { id: "int-csv", name: "CSV Upload", type: "csv", status: "connected", lastSync: "2026-04-30T20:58:00.000Z" },
  { id: "int-excel", name: "Excel", type: "excel", status: "available" },
  { id: "int-shopify", name: "Shopify", type: "shopify", status: "available" },
  { id: "int-meta", name: "Meta Ads", type: "meta", status: "coming_soon" },
  { id: "int-google", name: "Google Ads", type: "google_ads", status: "coming_soon" },
  { id: "int-crm", name: "HubSpot CRM", type: "crm", status: "coming_soon" },
  { id: "int-erp", name: "SAP ERP", type: "erp", status: "coming_soon" },
];

import { create } from "zustand";
import type { TimeRange, SystemMode, KpiData, Decision, Segment, NarrationData } from "@/lib/types";
import type { AnalyzeResponse } from "@/services/apiClient";

interface AegisState {
  /* Focus Mode */
  focusId: string | null;
  setFocus: (id: string | null) => void;
  isFocused: (id: string) => boolean;
  isDimmed: (id: string) => boolean;

  /* Time Range */
  timeRange: TimeRange;
  setTimeRange: (range: TimeRange) => void;

  /* System Mode */
  systemMode: SystemMode;
  setSystemMode: (mode: SystemMode) => void;

  /* Sidebar */
  sidebarExpanded: boolean;
  setSidebarExpanded: (expanded: boolean) => void;

  /* Crosshair sync */
  crosshairIndex: number | null;
  setCrosshairIndex: (index: number | null) => void;

  /* Auth / Tenant */
  apiKey: string;
  setApiKey: (key: string) => void;
  tenantId: string | null;
  setTenantId: (id: string | null) => void;

  /* Analysis State */
  rawAnalysis: AnalyzeResponse | null;
  setRawAnalysis: (data: AnalyzeResponse | null) => void;
  analysisLoading: boolean;
  setAnalysisLoading: (loading: boolean) => void;
  analysisError: string | null;
  setAnalysisError: (error: string | null) => void;
  currentDomain: string;
  setCurrentDomain: (domain: string) => void;

  /* Transformed UI Data */
  kpis: KpiData[];
  setKpis: (kpis: KpiData[]) => void;
  decisions: Decision[];
  setDecisions: (decisions: Decision[]) => void;
  segments: Segment[];
  setSegments: (segments: Segment[]) => void;
  narration: NarrationData | null;
  setNarration: (narration: NarrationData | null) => void;
  chartData: Array<Record<string, unknown>>;
  setChartData: (data: Array<Record<string, unknown>>) => void;
  headline: string;
  setHeadline: (headline: string) => void;
  confidence: number;
  setConfidence: (confidence: number) => void;

  /* Upload State */
  uploadProgress: number;
  setUploadProgress: (progress: number) => void;
  uploadStage: string;
  setUploadStage: (stage: string) => void;

  /* Backend Status */
  backendOnline: boolean;
  setBackendOnline: (online: boolean) => void;
  llmAvailable: boolean;
  setLlmAvailable: (available: boolean) => void;
}

export const useAegisStore = create<AegisState>((set, get) => ({
  focusId: null,
  setFocus: (id) => set({ focusId: id }),
  isFocused: (id) => get().focusId === id,
  isDimmed: (id) => get().focusId !== null && get().focusId !== id,

  timeRange: "30D",
  setTimeRange: (range) => set({ timeRange: range }),

  systemMode: "DETERMINISTIC",
  setSystemMode: (mode) => set({ systemMode: mode }),

  sidebarExpanded: false,
  setSidebarExpanded: (expanded) => set({ sidebarExpanded: expanded }),

  crosshairIndex: null,
  setCrosshairIndex: (index) => set({ crosshairIndex: index }),

  // Auth
  apiKey: "",
  setApiKey: (key) => {
    if (typeof window !== "undefined") localStorage.setItem("aegis_api_key", key);
    set({ apiKey: key });
  },
  tenantId: null,
  setTenantId: (id) => set({ tenantId: id }),

  // Analysis
  rawAnalysis: null,
  setRawAnalysis: (data) => set({ rawAnalysis: data }),
  analysisLoading: false,
  setAnalysisLoading: (loading) => set({ analysisLoading: loading }),
  analysisError: null,
  setAnalysisError: (error) => set({ analysisError: error }),
  currentDomain: "general",
  setCurrentDomain: (domain) => set({ currentDomain: domain }),

  // Transformed Data
  kpis: [],
  setKpis: (kpis) => set({ kpis }),
  decisions: [],
  setDecisions: (decisions) => set({ decisions }),
  segments: [],
  setSegments: (segments) => set({ segments }),
  narration: null,
  setNarration: (narration) => set({ narration }),
  chartData: [],
  setChartData: (data) => set({ chartData: data }),
  headline: "Upload data to begin analysis",
  setHeadline: (headline) => set({ headline }),
  confidence: 0,
  setConfidence: (confidence) => set({ confidence }),

  // Upload
  uploadProgress: 0,
  setUploadProgress: (progress) => set({ uploadProgress: progress }),
  uploadStage: "",
  setUploadStage: (stage) => set({ uploadStage: stage }),

  // Backend
  backendOnline: false,
  setBackendOnline: (online) => set({ backendOnline: online }),
  llmAvailable: false,
  setLlmAvailable: (available) => set({ llmAvailable: available }),
}));

"use client";

import { useCallback, useRef } from "react";
import { useAegisStore } from "@/store/aegisStore";
import { analyzeData, checkHealth, checkLLMHealth } from "@/services/apiClient";
import {
  transformKpis,
  transformDecisions,
  transformSegments,
  transformNarration,
  transformChartData,
  extractHeadline,
  extractConfidence,
} from "@/services/dataTransformer";

const UPLOAD_STAGES = [
  "Uploading file...",
  "Profiling dataset...",
  "Semantic mapping...",
  "Building baseline...",
  "Detecting signals...",
  "Analyzing bias patterns...",
  "Computing confidence...",
  "Cross-metric validation...",
  "Synthesizing decisions...",
  "Generating narration...",
];

export function useAnalysis() {
  // Select ONLY the specific values we need — prevents infinite re-render loop.
  // useAegisStore() as a whole returns a new object ref every render,
  // but individual selectors are stable via Zustand's shallow equality.
  const analysisLoading = useAegisStore((s) => s.analysisLoading);
  const analysisError = useAegisStore((s) => s.analysisError);
  const rawAnalysis = useAegisStore((s) => s.rawAnalysis);
  const uploadProgress = useAegisStore((s) => s.uploadProgress);
  const uploadStage = useAegisStore((s) => s.uploadStage);
  const currentDomain = useAegisStore((s) => s.currentDomain);

  // Use a ref to track the stage interval so it survives across renders
  const stageIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const runAnalysis = useCallback(async (file: File, domain?: string) => {
    const store = useAegisStore.getState();
    const targetDomain = domain || store.currentDomain;

    // Guard against double-submission
    if (store.analysisLoading) {
      console.warn("[AEGIS] Analysis already in progress, ignoring duplicate call");
      return;
    }

    // Set loading state
    useAegisStore.setState({
      analysisLoading: true,
      analysisError: null,
      uploadProgress: 0,
      uploadStage: UPLOAD_STAGES[0],
    });

    // Simulate stage progression while waiting for the backend
    let stageIdx = 0;
    stageIntervalRef.current = setInterval(() => {
      stageIdx = Math.min(stageIdx + 1, UPLOAD_STAGES.length - 1);
      useAegisStore.setState({
        uploadStage: UPLOAD_STAGES[stageIdx],
        uploadProgress: Math.round(((stageIdx + 1) / UPLOAD_STAGES.length) * 100),
      });
    }, 2500);

    try {
      console.log(`[AEGIS] Starting analysis: domain=${targetDomain} file=${file.name} size=${file.size}`);
      const response = await analyzeData(targetDomain, file);
      console.log(`[AEGIS] Analysis complete: status=${response.status} state=${response.system_state} decisions=${response.final_decisions?.length}`);

      // Clear stage animation
      if (stageIntervalRef.current) clearInterval(stageIntervalRef.current);

      // Transform and hydrate store in one batch
      useAegisStore.setState({
        uploadProgress: 100,
        uploadStage: "Complete",
        rawAnalysis: response,
        currentDomain: targetDomain,
        kpis: transformKpis(response),
        decisions: transformDecisions(response),
        segments: transformSegments(response),
        narration: transformNarration(response),
        chartData: transformChartData(response),
        headline: extractHeadline(response),
        confidence: extractConfidence(response),
        systemMode: response.narration_meta?.mode === "llm" ? "LLM_AUGMENTED" : "DETERMINISTIC",
        tenantId: response.tenant || null,
        analysisLoading: false,
        analysisError: null,
      });

      return response;
    } catch (err) {
      console.error("[AEGIS] Analysis failed:", err);
      if (stageIntervalRef.current) clearInterval(stageIntervalRef.current);

      const message = err instanceof Error ? err.message : "Analysis failed — check your API key and backend connection.";
      useAegisStore.setState({
        analysisLoading: false,
        analysisError: message,
        uploadProgress: 0,
        uploadStage: "",
      });

      throw err;
    }
  }, []); // Empty deps — uses getState() so no dependency on store object

  const checkBackend = useCallback(async () => {
    try {
      await checkHealth();
      useAegisStore.setState({ backendOnline: true });
    } catch {
      useAegisStore.setState({ backendOnline: false });
    }

    try {
      const llm = await checkLLMHealth();
      useAegisStore.setState({ llmAvailable: llm.available });
    } catch {
      useAegisStore.setState({ llmAvailable: false });
    }
  }, []); // Empty deps — stable across renders

  return {
    runAnalysis,
    checkBackend,
    isLoading: analysisLoading,
    error: analysisError,
    hasData: rawAnalysis !== null,
    uploadProgress,
    uploadStage,
  };
}

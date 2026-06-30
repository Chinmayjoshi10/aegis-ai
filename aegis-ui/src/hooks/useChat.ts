"use client";

import { useState, useCallback, useRef } from "react";
import { useAegisStore } from "@/store/aegisStore";
import { chat as chatApi, warmupLLM, AegisApiError } from "@/services/apiClient";
import type { ChatMessage, Citation } from "@/lib/types";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  // Guard: prevent overlapping sends if the user spams the button.
  const inflight = useRef(false);

  const sendMessage = useCallback(async (question: string) => {
    if (!question.trim() || inflight.current) return;

    const analysis = useAegisStore.getState().rawAnalysis?.analysis || {};
    if (!analysis || Object.keys(analysis).length === 0) {
      setMessages((prev) => [
        ...prev,
        {
          id: `msg-${Date.now()}`,
          role: "user",
          content: question,
          timestamp: new Date().toISOString(),
        },
        {
          id: `msg-${Date.now() + 1}`,
          role: "assistant",
          content:
            "No analysis is loaded. Upload a dataset on the Dashboard first — chat answers are grounded in the structured analysis output.",
          confidence: 0,
          timestamp: new Date().toISOString(),
        },
      ]);
      return;
    }

    inflight.current = true;
    setLoading(true);

    setMessages((prev) => [
      ...prev,
      {
        id: `msg-${Date.now()}`,
        role: "user",
        content: question,
        timestamp: new Date().toISOString(),
      },
    ]);

    try {
      const response = await chatApi(question, analysis);

      const citations: Citation[] = (response.signals_used || []).map((sigId, i) => ({
        id: `cite-${Date.now()}-${i}`,
        label: sigId,
        targetId: `kpi-${sigId}`,
        type: "signal" as const,
      }));

      // Confidence: high when the LLM grounded against signals; medium when the
      // deterministic keyword fallback ran (still grounded, but coarser).
      const confidence =
        response.source === "gemma" ? 90 : response.source === "keyword_fallback" ? 70 : 50;

      setMessages((prev) => [
        ...prev,
        {
          id: `msg-${Date.now() + 1}`,
          role: "assistant",
          content: response.answer,
          citations: citations.length > 0 ? citations : undefined,
          confidence,
          timestamp: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      // Classify the failure so the user gets actionable feedback instead of
      // a generic "backend may be offline" string.
      let content: string;
      if (err instanceof AegisApiError) {
        if (err.status === 0) {
          content =
            "The model is taking longer than expected (likely cold-loading). " +
            "Try the 'Warm up model' action and resend — subsequent requests run at full speed.";
        } else if (err.status === 401) {
          content = "Authentication failed. Set your API key in the header dropdown and try again.";
        } else if (err.status >= 500) {
          content = `Backend error (${err.status}): ${err.detail}. Check the FastAPI logs.`;
        } else {
          content = `Request rejected (${err.status}): ${err.detail}.`;
        }
      } else {
        content = `Unable to process query: ${err instanceof Error ? err.message : "Unknown error"}.`;
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `msg-${Date.now() + 1}`,
          role: "assistant",
          content,
          confidence: 0,
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      inflight.current = false;
      setLoading(false);
    }
  }, []);

  // Optional: manually preload the model so the first chat is fast.
  const warmup = useCallback(async () => {
    try {
      const res = await warmupLLM();
      return res;
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  }, []);

  const clearChat = useCallback(() => setMessages([]), []);

  return { messages, sendMessage, loading, clearChat, warmup };
}

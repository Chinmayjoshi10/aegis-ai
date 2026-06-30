/** AEGIS API Client — Centralized backend connector
 *
 * Single source of truth for all backend communication.
 * Handles auth headers, tenant context, retries, and error normalization.
 */

const API_BASE = process.env.NEXT_PUBLIC_AEGIS_API_URL || "http://127.0.0.1:8000";

export class AegisApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public endpoint: string,
  ) {
    super(`[AEGIS API] ${status} ${endpoint}: ${detail}`);
    this.name = "AegisApiError";
  }
}

interface RequestOptions {
  method?: string;
  body?: FormData | string;
  headers?: Record<string, string>;
  timeout?: number;
  retries?: number;
}

/** Read API key from localStorage (safe for client-only usage) */
function getApiKey(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("aegis_api_key") || "";
}

async function request<T>(
  endpoint: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, headers = {}, timeout = 120000, retries = 2 } = options;

  const apiKey = getApiKey();

  const defaultHeaders: Record<string, string> = {
    "X-API-Key": apiKey,
    ...headers,
  };

  // Don't set Content-Type for FormData — browser handles multipart boundary
  if (typeof body === "string") {
    defaultHeaders["Content-Type"] = "application/json";
  }

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retries; attempt++) {
    // Fresh AbortController for each attempt — avoids poisoned-signal bug
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method,
        headers: defaultHeaders,
        body,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({ detail: response.statusText }));
        throw new AegisApiError(response.status, errorBody.detail || response.statusText, endpoint);
      }

      return (await response.json()) as T;
    } catch (err) {
      clearTimeout(timeoutId);
      lastError = err as Error;

      // Don't retry client errors (4xx) or AbortErrors
      if (err instanceof AegisApiError && err.status < 500) throw err;
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new AegisApiError(0, `Request timed out after ${timeout}ms`, endpoint);
      }

      // Backoff before retry
      if (attempt < retries) {
        console.warn(`[AEGIS API] Attempt ${attempt + 1} failed for ${endpoint}, retrying in ${(attempt + 1)}s...`);
        await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
      }
    }
  }

  throw lastError || new Error("Request failed");
}

// ─── Health ────────────────────────────────────
export async function checkHealth() {
  return request<{ status: string; version: string }>("/health", { retries: 0, timeout: 5000 });
}

export async function checkLLMHealth() {
  return request<{
    available: boolean;
    latency_ms: number;
    model: string;
    model_installed?: boolean;
    model_loaded?: boolean;
    installed_models?: string[];
    error?: string | null;
  }>("/health/llm", { retries: 0, timeout: 10000 });
}

export async function warmupLLM() {
  return request<{ ok: boolean; elapsed_ms?: number; model?: string; loaded?: boolean; error?: string }>(
    "/health/llm/warmup",
    { method: "POST", retries: 0, timeout: 240000 },
  );
}

// ─── Analysis ──────────────────────────────────
export interface AnalyzeResponse {
  status: string;
  tenant: string;
  domain: string;
  data_mode: string;
  profile: {
    time_column: string | null;
    valid_metrics: string[];
    dimensions: string[];
    data_quality_score: number;
    row_count: number;
    warnings: string[];
  };
  system_state: string;
  narrative: string;
  company_insights: Array<Record<string, unknown>>;
  final_decisions: Array<{
    source: string;
    type: string;
    title: string;
    summary: string;
    action: string;
    priority: string;
    confidence: number;
    impact: number;
    signals: string[];
    metric: string;
  }>;
  global_decisions: Array<Record<string, unknown>>;
  segment_decisions: Record<string, unknown>;
  decision_cards: Array<Record<string, unknown>>;
  aegis_insights: Array<Record<string, unknown>>;
  descriptive_insights: Array<Record<string, unknown>>;
  relative_decisions: Array<Record<string, unknown>>;
  forecasts: Record<string, unknown>;
  drift_report: Record<string, unknown>;
  quality_report: Record<string, unknown>;
  reality_snapshot: {
    numeric: Record<string, {
      mean: number;
      median: number;
      std: number;
      min: number;
      max: number;
    }>;
  };
  semantic_mappings: Record<string, string>;
  metadata: Record<string, unknown>;
  analysis: Record<string, unknown>;
  narration: string;
  narration_meta: Record<string, unknown>;
}

export async function analyzeData(domain: string, file: File): Promise<AnalyzeResponse> {
  const formData = new FormData();
  formData.append("file", file);

  return request<AnalyzeResponse>(`/api/analyze/${domain}`, {
    method: "POST",
    body: formData,
    timeout: 300000, // 5 min for large files
    retries: 0,      // No retry for uploads — file body cannot be re-read after consumption
  });
}

// ─── Chat ──────────────────────────────────────
export interface ChatResponse {
  answer: string;
  grounded: boolean;
  source: string;
  mode: string;
  signals_used?: string[];
}

export async function chat(question: string, analysis: Record<string, unknown>): Promise<ChatResponse> {
  // 240s ceiling: covers cold-load (~90-180s on modest hardware) plus a typical
  // warm chat call (~30s). Single-shot — never silent-retry an LLM call.
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ question, analysis }),
    timeout: 240000,
    retries: 0,
  });
}

// ─── Monitoring ────────────────────────────────
export async function getMonitoring(domain: string) {
  return request<Record<string, unknown>>(`/monitor/${domain}`);
}

// ─── Ingest (webhook) ──────────────────────────
export async function ingest(port: string, payload: Record<string, unknown>) {
  return request<{ status: string; intelligence: Record<string, unknown> }>(`/ingest/${port}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

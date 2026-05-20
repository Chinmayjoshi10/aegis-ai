"""
aegis_ai.llm — LLM provider subsystem.

Providers:
    GeminiProvider   — Google Gemini API (cloud, default)
    OllamaProvider   — Local Ollama (self-hosted)

Facade:
    call_gemma()           — provider-agnostic generation
    is_gemma_available()   — provider health probe
    check_gemma_health()   — detailed health report
    warmup_gemma()         — preload / verify connectivity

Provider selection via AEGIS_LLM_PROVIDER env var ("gemini" | "ollama").
"""

from aegis_ai.llm.call_gemma import (
    call_gemma,
    is_gemma_available,
    check_gemma_health,
    warmup_gemma,
    clear_cache,
    reset_provider,
)

# Legacy compat — keep call_llm available for old imports
def call_llm(prompt: str) -> str:
    return call_gemma(prompt)

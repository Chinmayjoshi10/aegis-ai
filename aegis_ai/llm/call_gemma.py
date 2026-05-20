"""
aegis_ai/llm/call_gemma.py
=============================
Provider-agnostic LLM facade for AEGIS.

Routes to either Gemini (cloud) or Ollama (local) based on env config:

    AEGIS_LLM_PROVIDER=gemini   →  Google Gemini API (default)
    AEGIS_LLM_PROVIDER=ollama   →  Local Ollama

Usage:
    from aegis_ai.llm.call_gemma import call_gemma
    response = call_gemma("Summarize this analysis: ...")

Features:
    - In-memory prompt cache (avoids duplicate LLM calls)
    - Health check with latency measurement
    - Lazy-init provider singleton
    - Provider-agnostic: all consumers use call_gemma() regardless of backend
"""

import hashlib
import logging
import os
import time
from typing import Any

log = logging.getLogger("aegis_ai.llm.call_gemma")

# Module-level singleton — reused across calls
_provider = None

# ─────────────────────────────────────────────────────────────────────────────
# IN-MEMORY CACHE — keyed by prompt hash
# ─────────────────────────────────────────────────────────────────────────────

_cache: dict[str, str] = {}
_CACHE_MAX_SIZE = 100  # evict oldest when exceeded


def _cache_key(prompt: str) -> str:
    """Stable hash of prompt string for cache lookup."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def clear_cache() -> int:
    """Clear the prompt cache. Returns count of entries cleared."""
    count = len(_cache)
    _cache.clear()
    return count


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER FACTORY — routes to Gemini or Ollama based on env config
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_provider_name() -> str:
    """
    Determine which provider to use.

    Priority:
      1. Explicit AEGIS_LLM_PROVIDER env var ("gemini" or "ollama")
      2. If AEGIS_GEMINI_API_KEY is set → gemini
      3. Fallback → ollama (legacy default)
    """
    explicit = os.getenv("AEGIS_LLM_PROVIDER", "").strip().lower()
    if explicit in ("gemini", "ollama"):
        return explicit

    # Auto-detect: prefer Gemini if API key is present
    if os.getenv("AEGIS_GEMINI_API_KEY", "").strip():
        return "gemini"

    return "ollama"


def _create_provider():
    """Instantiate the configured provider."""
    name = _resolve_provider_name()

    if name == "gemini":
        from aegis_ai.llm.gemini_provider import GeminiProvider
        log.info("[LLM] Using Gemini API provider")
        return GeminiProvider()
    else:
        from aegis_ai.llm.ollama_provider import OllamaProvider
        log.info("[LLM] Using Ollama local provider")
        return OllamaProvider()


def _get_provider():
    """Lazy-init the provider singleton."""
    global _provider
    if _provider is None:
        _provider = _create_provider()
    return _provider


def reset_provider():
    """Force re-creation of the provider (useful after config changes)."""
    global _provider
    _provider = None
    clear_cache()


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API — unchanged signatures for all consumers
# ─────────────────────────────────────────────────────────────────────────────

def call_gemma(
    prompt: str,
    timeout: int = 60,
    use_cache: bool = True,
) -> str:
    """
    Call the configured LLM provider and return the generated text.
    Uses in-memory cache to avoid duplicate calls for identical prompts.

    Args:
        prompt: The input prompt (structured JSON context + instruction)
        timeout: Request timeout in seconds
        use_cache: If True, check cache before calling LLM

    Returns:
        str: Generated text

    Raises:
        RuntimeError: If the LLM is unreachable or the model fails
    """
    # ── Cache check ───────────────────────────────────────────────────────
    if use_cache:
        key = _cache_key(prompt)
        cached = _cache.get(key)
        if cached is not None:
            log.info(f"[LLM] Cache hit, key={key[:12]}...")
            return cached

    # ── Call provider ─────────────────────────────────────────────────────
    provider = _get_provider()
    provider_name = type(provider).__name__
    log.info(f"[LLM] Calling provider={provider_name} model={provider.model} prompt_len={len(prompt)}")

    result = provider.generate(prompt, timeout=timeout)

    log.info(f"[LLM] Response received, len={len(result)}")

    # ── Cache store ───────────────────────────────────────────────────────
    if use_cache:
        # Simple eviction: clear entire cache if too large
        if len(_cache) >= _CACHE_MAX_SIZE:
            log.info(f"[LLM] Cache full ({_CACHE_MAX_SIZE}), clearing")
            _cache.clear()
        _cache[key] = result

    return result


def is_gemma_available() -> bool:
    """Check if the configured LLM provider is available."""
    try:
        return _get_provider().is_available()
    except Exception:
        return False


def check_gemma_health() -> dict[str, Any]:
    """
    Cheap health check for the configured LLM provider.

    Reports whether the API is reachable, the configured model is installed,
    and whether it is currently warm (resident in RAM / ready to serve).

    Returns:
        dict with: available, model, provider, model_installed, model_loaded,
                   installed_models, latency_ms, error
    """
    provider = _get_provider()
    provider_name = _resolve_provider_name()
    start = time.perf_counter()

    try:
        api_ok = provider.api_reachable()
        if not api_ok:
            return {
                "available":        False,
                "latency_ms":       round((time.perf_counter() - start) * 1000, 1),
                "model":            provider.model,
                "provider":         provider_name,
                "model_installed":  False,
                "model_loaded":     False,
                "installed_models": [],
                "error":            f"{provider_name} API not reachable. Check your configuration.",
            }

        installed = provider.installed_models()
        model_installed = provider.model in installed or provider_name == "gemini"
        model_loaded = provider.model_loaded() if model_installed else False
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)

        if not model_installed:
            return {
                "available":        False,
                "latency_ms":       elapsed_ms,
                "model":            provider.model,
                "provider":         provider_name,
                "model_installed":  False,
                "model_loaded":     False,
                "installed_models": installed,
                "error":            f"Configured model '{provider.model}' not found.",
            }

        return {
            "available":        True,
            "latency_ms":       elapsed_ms,
            "model":            provider.model,
            "provider":         provider_name,
            "model_installed":  True,
            "model_loaded":     model_loaded,
            "installed_models": installed if provider_name == "ollama" else [provider.model],
            "error":            None,
        }

    except Exception as e:
        return {
            "available":        False,
            "latency_ms":       round((time.perf_counter() - start) * 1000, 1),
            "model":            provider.model,
            "provider":         provider_name,
            "model_installed":  False,
            "model_loaded":     False,
            "installed_models": [],
            "error":            str(e),
        }


def warmup_gemma() -> dict[str, Any]:
    """Trigger a provider warmup. Idempotent."""
    return _get_provider().warmup()

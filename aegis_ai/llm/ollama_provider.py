"""
aegis_ai/llm/ollama_provider.py
=================================
HTTP-based Ollama provider for local LLM inference.

Uses the Ollama REST API (http://localhost:11434/api/generate) instead of
subprocess for robustness, proper timeout handling, and streaming support.

Model is configured via AEGIS_OLLAMA_MODEL env var.
"""

import os
import logging
import requests

log = logging.getLogger("aegis_ai.llm.ollama_provider")

_DEFAULT_MODEL = "llama3:latest"
_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_KEEP_ALIVE = "30m"


class OllamaProvider:
    """HTTP-based Ollama LLM provider."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        keep_alive: str | None = None,
    ):
        self.model = model or os.getenv("AEGIS_OLLAMA_MODEL", _DEFAULT_MODEL)
        self.base_url = base_url or os.getenv("AEGIS_OLLAMA_URL", _DEFAULT_BASE_URL)
        self.keep_alive = keep_alive or os.getenv(
            "AEGIS_OLLAMA_KEEP_ALIVE", _DEFAULT_KEEP_ALIVE
        )

    # ── Cheap diagnostics ─────────────────────────────────────────────────────
    # Probe timeouts are generous because a recently-stressed Ollama daemon can
    # take several seconds to answer /api/tags even though it's healthy.

    _PROBE_TIMEOUT = 8

    def _fetch_tags(self) -> list[str] | None:
        """Single /api/tags call. Returns model name list, or None on failure."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=self._PROBE_TIMEOUT)
            if resp.status_code != 200:
                return None
            return [m.get("name", "") for m in resp.json().get("models", [])]
        except Exception:
            return None

    def api_reachable(self) -> bool:
        return self._fetch_tags() is not None

    def installed_models(self) -> list[str]:
        return self._fetch_tags() or []

    def model_installed(self) -> bool:
        tags = self._fetch_tags()
        return tags is not None and self.model in tags

    def model_loaded(self) -> bool:
        """Is the configured model currently resident in memory (warm)?"""
        try:
            resp = requests.get(f"{self.base_url}/api/ps", timeout=self._PROBE_TIMEOUT)
            if resp.status_code != 200:
                return False
            return any(m.get("name") == self.model for m in resp.json().get("models", []))
        except Exception:
            return False

    def is_available(self) -> bool:
        """API reachable AND configured model installed — single /api/tags call."""
        tags = self._fetch_tags()
        return tags is not None and self.model in tags

    # ── Inference ─────────────────────────────────────────────────────────────

    def generate(self, prompt: str, timeout: int = 180) -> str:
        """
        Generate text from the Ollama API.

        Uses keep_alive so the model stays resident in RAM between requests —
        first call after a cold start can take 60-120s on this hardware,
        subsequent calls run at normal eval speed.
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model":      self.model,
            "prompt":     prompt,
            "stream":     False,
            "keep_alive": self.keep_alive,
        }

        try:
            resp = requests.post(url, json=payload, timeout=timeout)

            if resp.status_code != 200:
                raise RuntimeError(
                    f"Ollama API error (HTTP {resp.status_code}): {resp.text[:300]}"
                )

            data = resp.json()
            return data.get("response", "").strip()

        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Is Ollama running? Start with: ollama serve"
            )
        except requests.exceptions.Timeout:
            raise RuntimeError(
                f"Ollama request timed out after {timeout}s. "
                "The model may be cold-loading; try POST /health/llm/warmup first."
            )
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Ollama provider error: {e}")

    def warmup(self, timeout: int = 240) -> dict:
        """
        Force the configured model to load into memory.
        Returns timing diagnostics. Idempotent — fast if already warm.
        """
        import time
        if not self.api_reachable():
            return {"ok": False, "error": f"Ollama API not reachable at {self.base_url}"}
        if not self.model_installed():
            return {
                "ok": False,
                "error": f"Model '{self.model}' not installed. "
                         f"Available: {self.installed_models()}",
            }

        start = time.perf_counter()
        try:
            # Empty prompt with keep_alive triggers a load without inference cost
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": "", "keep_alive": self.keep_alive, "stream": False},
                timeout=timeout,
            )
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            if resp.status_code != 200:
                return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}", "elapsed_ms": elapsed_ms}
            return {"ok": True, "elapsed_ms": elapsed_ms, "model": self.model, "loaded": self.model_loaded()}
        except requests.exceptions.Timeout:
            return {"ok": False, "error": f"warmup timed out after {timeout}s — likely insufficient RAM/VRAM for model"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

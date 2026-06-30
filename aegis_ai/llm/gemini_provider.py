"""
aegis_ai/llm/gemini_provider.py
=================================
Google Gemini API provider for cloud-based LLM inference.

Uses the google-genai SDK to call the Gemini API, providing the same
interface as OllamaProvider so the two are interchangeable.

Configuration via environment:
    AEGIS_GEMINI_API_KEY   — your Gemini API key (required)
    AEGIS_GEMINI_MODEL     — model name (default: gemini-2.0-flash)
"""

import os
import logging
import time

log = logging.getLogger("aegis_ai.llm.gemini_provider")

_DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiProvider:
    """Cloud-based Gemini LLM provider — drop-in replacement for OllamaProvider."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        self.model = model or os.getenv("AEGIS_GEMINI_MODEL", _DEFAULT_MODEL)
        self._api_key = api_key or os.getenv("AEGIS_GEMINI_API_KEY", "")
        self._client = None

        if not self._api_key:
            log.warning(
                "[GEMINI] No API key found. Set AEGIS_GEMINI_API_KEY in .env. "
                "LLM features will be unavailable."
            )

    def _get_client(self):
        """Lazy-init the Gemini client singleton."""
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def api_reachable(self) -> bool:
        """Check if the Gemini API is reachable."""
        if not self._api_key:
            return False
        try:
            client = self._get_client()
            # Lightweight probe — list available models
            client.models.list(config={"page_size": 1})
            return True
        except Exception as e:
            log.debug(f"[GEMINI] API probe failed: {e}")
            return False

    def installed_models(self) -> list[str]:
        """Return available model names (Gemini always has its models)."""
        if not self._api_key:
            return []
        try:
            client = self._get_client()
            models = client.models.list()
            return [m.name for m in models]
        except Exception:
            return []

    def model_installed(self) -> bool:
        return self.is_available()

    def model_loaded(self) -> bool:
        """Gemini models are always 'loaded' — no cold start."""
        return self.is_available()

    def is_available(self) -> bool:
        """API key present and API reachable."""
        if not self._api_key:
            return False
        return self.api_reachable()

    # ── Inference ─────────────────────────────────────────────────────────────

    def generate(self, prompt: str, timeout: int = 60) -> str:
        """
        Generate text from the Gemini API.

        Args:
            prompt: The input prompt
            timeout: Not directly used (Gemini SDK handles its own timeouts),
                     kept for interface compatibility

        Returns:
            str: Generated text

        Raises:
            RuntimeError: If the API key is missing or the call fails
        """
        if not self._api_key:
            raise RuntimeError(
                "Gemini API key not configured. "
                "Set AEGIS_GEMINI_API_KEY in your .env file."
            )

        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            text = response.text or ""
            return text.strip()

        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}") from e

    def warmup(self, timeout: int = 30) -> dict:
        """
        Verify API connectivity. Gemini has no cold start, so this is a
        lightweight reachability check.
        """
        start = time.perf_counter()
        if not self._api_key:
            return {"ok": False, "error": "No Gemini API key configured"}

        try:
            reachable = self.api_reachable()
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            if reachable:
                return {
                    "ok": True,
                    "elapsed_ms": elapsed_ms,
                    "model": self.model,
                    "loaded": True,
                    "provider": "gemini",
                }
            return {
                "ok": False,
                "error": "Gemini API not reachable",
                "elapsed_ms": elapsed_ms,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

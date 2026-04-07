import os
import shutil


class RootCauseAgent:
    def __init__(self):
        """Root cause analysis is optional.

        This agent MUST NOT block the cognition pipeline if the local LLM stack
        (Ollama) is unavailable or slow. We therefore:
        - require the `ollama` executable to be present
        - enforce a short timeout
        - degrade gracefully to a deterministic placeholder
        """

        # Keep this short so the cognition pipeline never stalls.
        self.timeout_s = int(os.environ.get("AEGIS_OLLAMA_TIMEOUT", "1"))

        # Hard-gate on executable presence to prevent hangs.
        if shutil.which("ollama") is None:
            self.brain = None
            return

        try:
            from aegis_ai.llm.ollama_provider import OllamaProvider
            from aegis_ai.brains.root_cause_brain import RootCauseBrain

            provider = OllamaProvider(model=os.environ.get("AEGIS_OLLAMA_MODEL", "llama3"))
            self.brain = RootCauseBrain(provider)
        except Exception:
            self.brain = None  # LLM layer not ready yet

    def run(self, state: dict):
        print("AEGIS: RootCauseAgent - Checking for LLM capability...")

        if self.brain is None:
            print("AEGIS: RootCauseAgent skipped (LLM not active)")
            state["root_cause"] = "LLM root cause layer not active yet"

            state.setdefault("intelligence", {})
            state["intelligence"]["root_causes"] = state["root_cause"]
            return state

        try:
            explanation = self.brain.analyze(state, timeout=self.timeout_s)
            state["root_cause"] = explanation
        except Exception as e:
            print(f"AEGIS: RootCauseAgent error: {e}")
            state["root_cause"] = "Root cause analysis failed"

        state.setdefault("intelligence", {})
        state["intelligence"]["root_causes"] = state["root_cause"]

        return state

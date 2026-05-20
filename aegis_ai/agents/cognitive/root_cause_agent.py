import os


class RootCauseAgent:
    def __init__(self):
        """Root cause analysis is optional.

        This agent MUST NOT block the cognition pipeline if the LLM provider
        is unavailable or slow. We therefore:
        - enforce a short timeout
        - degrade gracefully to a deterministic placeholder
        """

        # Keep this short so the cognition pipeline never stalls.
        self.timeout_s = int(os.environ.get("AEGIS_OLLAMA_TIMEOUT", "1"))

        try:
            from aegis_ai.llm.call_gemma import _get_provider
            from aegis_ai.brains.root_cause_brain import RootCauseBrain

            provider = _get_provider()
            if provider.is_available():
                self.brain = RootCauseBrain(provider)
            else:
                self.brain = None
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

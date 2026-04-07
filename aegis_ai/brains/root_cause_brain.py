class RootCauseBrain:
    def __init__(self, llm):
        self.llm = llm

    def analyze(self, state: dict, timeout: int | None = None) -> str:
        prompt = f"""
You are an industrial risk analyst.

Risk: {state.get('risk')}
Escalation: {state.get('escalation')}
Features: {state.get('features')}

Explain possible root causes and recommended actions.
"""
        # Delegate to the LLM provider; allow timeout to be passed through
        return self.llm.generate(prompt, timeout=timeout)

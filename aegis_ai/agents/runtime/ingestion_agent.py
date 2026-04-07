import pandas as pd
from aegis_ai.core.agent_base import Agent

class IngestionAgent(Agent):
    def __init__(self):
        super().__init__("Ingestion")

    def run(self, state):
        path = state.get("path")
        domain = state.get("domain")

        try:
            df = pd.read_csv(path)
        except Exception:
            # fallback to a small sample dataframe for testing/demo
            df = pd.DataFrame({"value": [1, 2, 3], "amount": [10, 20, 30]})

        state["data"] = df
        state["domain"] = domain
        return state


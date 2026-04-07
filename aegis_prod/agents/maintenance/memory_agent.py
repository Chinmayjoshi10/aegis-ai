from aegis_ai.memory.memory_router import memory_backend

class MemoryAgent:
    def run(self, state):
        tenant = state["tenant"]

        if "semantic_contract" in state:
            memory_backend.store_contract(tenant, state["semantic_contract"])


        if "drift_score" in state:
            memory_backend.store_drift(tenant, state["drift_score"], state.get("root_cause"))

        if "forecast" in state:
            memory_backend.store_forecast(tenant, state["forecast"])

        if "escalation" in state:
            memory_backend.store_action(tenant, state["escalation"])

        return state

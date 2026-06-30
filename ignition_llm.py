import pandas as pd
import asyncio

from aegis_ai.core.decision_kernel import DecisionKernel
from aegis_ai.brains.semantic_intake_brain import SemanticIntakeBrain
from aegis_ai.agents.discovery_agent import DiscoveryAgent

df = pd.DataFrame({
    "furnace_temp": [72, 81, 94, 101],
    "co2_ppm": [410, 445, 480, 550],
    "power_kw": [1200, 1180, 1100, 980]
})

state = {
    "tenant": "mittal_pigments",
    "data": df
}

kernel = DecisionKernel()
kernel.register(DiscoveryAgent())
kernel.register(SemanticIntakeBrain())   # 🧠 LLM cognition layer ONLY

final_state = asyncio.run(kernel.run(state))

print("\n===== AEGIS SEMANTIC CORTEX OUTPUT =====\n")
print(final_state["semantic_intake"])

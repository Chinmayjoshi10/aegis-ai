import pandas as pd
import asyncio

from aegis_ai.core.decision_kernel import DecisionKernel

from aegis_ai.agents.discovery_agent import DiscoveryAgent
from aegis_ai.brains.semantic_intake_brain import SemanticIntakeBrain
from aegis_ai.agents.root_cause_agent import RootCauseAgent
from aegis_ai.agents.memory_agent import MemoryAgent


kernel = DecisionKernel()
kernel.register(DiscoveryAgent())
kernel.register(SemanticIntakeBrain())
kernel.register(RootCauseAgent())
kernel.register(MemoryAgent())


state = {
    "tenant": "mittal_pigments",
    "raw_input": "value,amount\n1,10\n2,20\n3,30",
    "data": pd.DataFrame({
        "value": [1, 2, 3],
        "amount": [10, 20, 30]
    })
}

asyncio.run(kernel.run(state))

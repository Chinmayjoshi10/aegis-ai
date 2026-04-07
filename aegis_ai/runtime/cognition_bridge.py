# aegis_ai/runtime/cognition_bridge.py

from typing import Dict, Any
from aegis_ai.core.decision_kernel import DecisionKernel


class CognitionBridge:
    """
    Runtime cognition executor.

    Does NOT import API.
    Does NOT use global state.
    Receives everything explicitly.
    """

    def __init__(self, kernel: DecisionKernel):
        self.kernel = kernel

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return self.kernel.run(state)
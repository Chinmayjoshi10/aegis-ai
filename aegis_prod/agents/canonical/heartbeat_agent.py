# aegis_ai/agents/heartbeat_agent.py

from typing import Dict, Any
from aegis_ai.core.agent_base import Agent


class HeartbeatAgent(Agent):
    """
    Canonical deterministic heartbeat agent.

    Responsibilities:
    - Signal kernel execution
    - Attach minimal structured liveness metadata

    Guarantees:
    - No I/O
    - No database access
    - No wall-clock usage
    - No randomness
    - No global state
    - Replay-safe
    - Tenant-safe
    - O(1) runtime
    """

    def __init__(self) -> None:
        super().__init__("Heartbeat")

    # ─────────────────────────────────────────────
    # CORE EXECUTION
    # ─────────────────────────────────────────────
    def run(self, state: Dict[str, Any]) -> None:

        intelligence = state.setdefault("intelligence", {})

        intelligence["heartbeat"] = {
            "alive": True
        }

        # Backward compatibility flag (allowed exception)
        state["kernel_alive"] = True

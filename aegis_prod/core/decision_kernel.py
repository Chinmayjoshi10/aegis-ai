from typing import Dict, Any
from copy import deepcopy
import json
import hashlib

from aegis_ai import __version__
from aegis_ai.connectors.enterprise_gateway import EnterpriseGateway
from aegis_ai.utils.clock import AegisClock


class DecisionKernel:
    """
    Central nervous kernel of AEGIS.

    Guarantees:
    - Deterministic execution
    - Stateless behavior
    - Replay-safe
    - Failure-isolated agents
    - Versioned output
    - Auditable hash integrity
    """

    def __init__(self):
        self.gateway = EnterpriseGateway()
        self.agents = []

    # ─────────────────────────────────────────────
    # AGENT REGISTRY
    # ─────────────────────────────────────────────
    def register(self, agent):
        self.agents.append(agent)

    # ─────────────────────────────────────────────
    # CORE RUN LOOP (DETERMINISTIC)
    # ─────────────────────────────────────────────
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes all registered agents on shared organism state.
        """

        # Defensive copy for replay safety
        state = deepcopy(state)

        # Ensure containers exist
        state.setdefault("intelligence", {})
        state.setdefault("system_logs", [])

        # ─────────────────────────────────────────────
        # Deterministic Clock Injection
        # ─────────────────────────────────────────────
        clock = AegisClock(fixed_time=state.get("_fixed_time"))
        state["_clock"] = clock
        # ─────────────────────────────────────────────

        # Execute agents in strict order
        for agent in self.agents:
            try:
                agent.run(state)
            except Exception as e:
                state["system_logs"].append(
                    f"[AGENT_FAILURE] {agent.__class__.__name__}: {str(e)}"
                )

        # Remove internal control keys
        state.pop("_clock", None)
        state.pop("_fixed_time", None)

        # Extract intelligence
        output = state["intelligence"]

        # ─────────────────────────────────────────────
        # Version Tagging
        # ─────────────────────────────────────────────
        output["engine_version"] = __version__

        # ─────────────────────────────────────────────
        # Deterministic Audit Hash
        # ─────────────────────────────────────────────
        serialized = json.dumps(output, sort_keys=True, default=str)
        output["audit_hash"] = hashlib.sha256(serialized.encode()).hexdigest()

        return output
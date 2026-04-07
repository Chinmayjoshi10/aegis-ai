# aegis_ai/agents/regime_snapshot_recorder.py

from typing import Dict, Any
from copy import deepcopy


class RegimeSnapshotRecorder:
    """
    Canonical Snapshot Agent.

    Emits a deterministic snapshot of current regime context.
    Does NOT:
    - Persist
    - Track history
    - Use timestamps
    - Mutate external state
    - Store rolling buffers

    Purely attaches a snapshot for downstream cognitive layers.
    """

    def run(self, state: Dict[str, Any]) -> None:

        intelligence = state.setdefault("intelligence", {})
        regime = intelligence.get("regime")

        if not regime:
            return

        # Only snapshot current deterministic context
        intelligence["regime_snapshot"] = {
            "regime": deepcopy(regime),
            "escalation": deepcopy(intelligence.get("escalation")),
            "confidence": deepcopy(intelligence.get("confidence")),
        }

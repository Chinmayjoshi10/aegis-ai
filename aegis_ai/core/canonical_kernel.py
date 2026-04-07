# aegis_ai/core/canonical_kernel.py

from typing import Dict, Any

from aegis_ai.core.decision_kernel import DecisionKernel
from aegis_ai.agents.canonical.regime_segmenter import RegimeSegmenter
from aegis_ai.agents.canonical.segmented_confidence_gate import SegmentedConfidenceGate
from aegis_ai.agents.canonical.escalation_agent import EscalationAgent
from aegis_ai.agents.canonical.segmented_tradeoff_detector import SegmentedTradeoffDetector
from aegis_ai.agents.canonical.regime_snapshot_recorder import RegimeSnapshotRecorder
from aegis_ai.agents.canonical.heartbeat_agent import HeartbeatAgent


def build_canonical_kernel() -> DecisionKernel:
    """
    Builds the production-locked canonical control kernel.

    Guarantees:
    - Deterministic execution
    - Stateless behavior
    - No time dependency
    - No persistence
    - No external I/O
    - Domain-agnostic
    - Replay-safe

    This kernel is frozen for production.
    """

    kernel = DecisionKernel()

    # ─────────────────────────────────────────────
    # Ordered Registration (DO NOT CHANGE ORDER)
    # ─────────────────────────────────────────────
    kernel.register(RegimeSegmenter())
    kernel.register(SegmentedConfidenceGate())
    kernel.register(EscalationAgent())
    kernel.register(SegmentedTradeoffDetector())
    kernel.register(RegimeSnapshotRecorder())
    kernel.register(HeartbeatAgent())

    return kernel

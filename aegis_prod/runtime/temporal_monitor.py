import time
import numpy as np

from aegis_ai.spine.event_store import EventStore
from aegis_ai.core.decision_kernel import DecisionKernel

from aegis_ai.agents.canonical.regime_segmenter import RegimeSegmenter
from aegis_ai.agents.canonical.regime_snapshot_recorder import RegimeSnapshotRecorder
from aegis_ai.agents.canonical.segmented_tradeoff_detector import SegmentedTradeoffDetector
from aegis_ai.agents.canonical.segmented_confidence_gate import SegmentedConfidenceGate


WINDOW_DAYS = 14
STEP_DAYS = 7
MOVING_AVG_K = 4
LOOKBACK_DAYS = 90


class TemporalMonitor:

    def __init__(self):
        self.store = EventStore()

    def _build_kernel(self):
        kernel = DecisionKernel()
        kernel.register(RegimeSegmenter())
        kernel.register(RegimeSnapshotRecorder())
        kernel.register(SegmentedTradeoffDetector())
        kernel.register(SegmentedConfidenceGate())
        return kernel

    def _compute_instability(self, state):

        drift_flags = state.get("drift_flags", [])
        tradeoff_flags = state.get("tradeoff_flags", [])
        system_state = state.get("system_state", "SILENT")
        escalation_velocity = state.get("escalation_velocity", 0)

        return (
            len(drift_flags)
            + len(tradeoff_flags)
            + (1 if system_state == "INSIGHTFUL" else 0)
            + float(escalation_velocity)
        )

    def run_for_domain(self, domain: str):

        now = time.time()
        start_ts = now - (LOOKBACK_DAYS * 86400)

        # Clear previous results (idempotent)
        self.store.clear_monitoring_results(domain)

        current_start = start_ts
        end_ts = now

        instability_history = []

        while current_start + (WINDOW_DAYS * 86400) <= end_ts:

            current_end = current_start + (WINDOW_DAYS * 86400)

            rows = self.store.get_events_between(
                domain,
                current_start,
                current_end
            )

            if not rows:
                current_start += STEP_DAYS * 86400
                continue

            state = {"physics": {}, "system_logs": []}

            kernel = self._build_kernel()
            gateway = kernel.gateway

            for event in rows:
                gateway.route_event(
                    domain=domain,
                    metric=event["metric"],
                    value=event["value"],
                    confidence=event["confidence"],
                    state=state,
                    physics=state["physics"]
                )

            kernel.run(state)

            instability_score = self._compute_instability(state)

            if len(instability_history) >= MOVING_AVG_K:
                moving_avg = np.mean(instability_history[-MOVING_AVG_K:])
            else:
                moving_avg = np.mean(instability_history) if instability_history else 0

            incident_flag = (
                moving_avg > 0 and
                instability_score >= 3 * moving_avg
            )

            instability_history.append(instability_score)

            self.store.save_monitoring_result(
                domain,
                current_start,
                current_end,
                instability_score,
                moving_avg,
                incident_flag,
                state.get("system_state", "UNKNOWN")
            )

            current_start += STEP_DAYS * 86400

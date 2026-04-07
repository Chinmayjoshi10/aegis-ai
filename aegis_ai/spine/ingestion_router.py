import time
from aegis_ai.spine.event_store import EventStore
from aegis_ai.spine.lineage_audit import LineageAudit

class IngestionRouter:
    """
    Fail-safe sensory firewall + forensic entry point.
    """

    IMPOSSIBLE_DROP = 0.75

    def __init__(self):
        self.store = EventStore()
        self.audit = LineageAudit()

    def clean(self, payload: dict, expected_schema: dict):
        clean = {}
        for key in expected_schema:
            try:
                clean[key] = float(payload.get(key, 0.0))
            except:
                clean[key] = 0.0
        return clean

    def continuity_check(self, last_state: dict, new_state: dict):
        for k in new_state:
            if k in last_state and last_state[k] > 0:
                drop = (last_state[k] - new_state[k]) / last_state[k]
                if drop > self.IMPOSSIBLE_DROP:
                    return False, k
        return True, None

    def route(self, payload: dict, source: str, state: dict, expected_schema: dict):
        cleaned = self.clean(payload, expected_schema)
        last = state.get("last_physics_snapshot", {})

        ok, bad_key = self.continuity_check(last, cleaned)

        if not ok:
            self.audit.log(payload, [], source, f"REJECT_{bad_key}")
            return {"accepted": False, "reason": f"IMPOSSIBLE_JUMP_{bad_key}", "confidence": 0.0}

        packet = {
            "accepted": True,
            "source": source,
            "clean": cleaned,
            "confidence": 1.0,
            "timestamp": time.time()
        }

        # FORENSIC ENTRY (always)
        audit_hash = self.audit.log(payload, cleaned, source, "ACCEPT")

        state.setdefault("ingestion_history", []).append(packet)
        state["ingestion_confidence"] = packet["confidence"]

        tenant = state.get("tenant_id") or state.get("tenant") or "default"

        # Ground truth commit with audit hash as causal key
        events = [{"domain": k.split("_")[0], "metric": k, "value": v, "audit": audit_hash}
                  for k, v in cleaned.items()]
        self.store.write(
            tenant=tenant,
            events=events,
            confidence=packet["confidence"]
        )

        return packet

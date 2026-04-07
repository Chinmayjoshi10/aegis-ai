import time
import hashlib
from collections import deque
from aegis_ai.connectors.universal_adapter import UniversalAdapter

from aegis_ai.spine.lineage_audit import LineageAudit



class WebhookAdapter:
    """
    Hardened Real-Time Sensory Nerve for AEGIS.
    """

    WINDOW = 300        # 5 minutes
    MAX_ERRORS = 5     # circuit breaker threshold

    def __init__(self):
        self.adapter = UniversalAdapter()
        self.audit = LineageAudit()
        self.recent_hashes = deque()
        self.error_times = deque()

    # ─────────────────────────────────────────────
    # Fast hash for deduplication
    # ─────────────────────────────────────────────
    def _hash(self, payload):
        return hashlib.md5(str(payload).encode()).hexdigest()

    # ─────────────────────────────────────────────
    # Non-blocking ingest
    # ─────────────────────────────────────────────
    def ingest(self, payload: dict, mapping: dict, state: dict, physics_state: dict,
               source="webhook", confidence=0.9):

        now = time.time()
        h = self._hash(payload)

        # ── Deduplication window
        self.recent_hashes = deque([x for x in self.recent_hashes if now - x[1] < self.WINDOW])
        if any(h == x[0] for x in self.recent_hashes):
            return  # fast fail

        self.recent_hashes.append((h, now))

        # ── Hysteresis: ignore stale payloads
        seq = payload.get("timestamp") or payload.get("sequence_id")
        last = state.get("last_webhook_seq", 0)
        if seq is not None and seq < last:
            return
        if seq:
            state["last_webhook_seq"] = seq

        try:
            # Forensic trace
            self.audit.log(payload, [], source, "WEBHOOK_ACCEPTED")

            # Inject into organism with reliability score
            self.adapter.inject(
                physics_state=physics_state,
                rows=[payload],
                mapping=mapping,
                source=source,
                confidence=confidence
            )

        except Exception:
            # Track failures
            self.error_times.append(now)
            self.error_times = deque([t for t in self.error_times if now - t < 60])

            if len(self.error_times) >= self.MAX_ERRORS:
                state.setdefault("physics", {})["sensor_integrity"] = 0.0

            # Fail fast, never block kernel
            return

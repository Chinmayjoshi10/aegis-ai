import hashlib
import json
import time


class AuditBrain:
    """
    Immutable enterprise decision ledger.
    """

    def __init__(self):
        self.ledger = []

    def _hash(self, record):
        blob = json.dumps(record, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    def log(self, state):
        record = {
            "timestamp": time.time(),
            "risk": state.get("risk"),
            "forecast": state.get("forecast"),
            "plans": state.get("plans"),
            "meta_decision": state.get("meta_decision"),
            "escalation": state.get("escalation"),
            "self_healing": state.get("self_healing_executed"),
        }
        record["hash"] = self._hash(record)
        self.ledger.append(record)

        print("📜 AUDIT LEDGER WRITE:", record["hash"])

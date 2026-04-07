import time, json, hashlib
from collections import deque

class LineageAudit:
    """
    Append-only forensic causality ledger for AEGIS.
    """

    def __init__(self, path="aegis_audit.log"):
        self.path = path
        self.last_normals = deque(maxlen=10)

    def _hash(self, record: dict):
        return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()

    def log(self, raw_payload, normalized_events, source, reason_code):
        base = {
            "ts": time.time(),
            "source": source,
            "reason": reason_code,
            "normalized": normalized_events
        }

        # ── Surgical logging (heartbeat collapse)
        if normalized_events in self.last_normals:
            record = {
                "ts": base["ts"],
                "source": source,
                "reason": "HEARTBEAT",
                "ref": self.last_normals[-1]
            }
        else:
            record = {
                **base,
                "raw": raw_payload
            }
            self.last_normals.append(normalized_events)

        h = self._hash(record)
        record["audit_hash"] = h

        with open(self.path, "a") as f:
            f.write(json.dumps(record) + "\n")

        return h

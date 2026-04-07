import json
import os
import hashlib
from datetime import datetime

class MemoryStore:
    def __init__(self, path="memory/history.json"):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

        if not os.path.exists(path):
            with open(path, "w") as f:
                genesis = {
                    "index": 0,
                    "timestamp": datetime.utcnow().isoformat(),
                    "risk": None,
                    "escalation": None,
                    "features": None,
                    "prev_hash": "GENESIS",
                    "hash": "GENESIS"
                }
                json.dump([genesis], f, indent=2)

    def _hash(self, record):
        payload = f"{record['index']}{record['timestamp']}{record['risk']}{record['escalation']}{record['features']}{record['prev_hash']}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def save(self, state: dict):
        with open(self.path, "r+") as f:
            history = json.load(f)
            last = history[-1]

            record = {
                "index": last["index"] + 1,
                "timestamp": datetime.utcnow().isoformat(),
                "risk": state.get("risk"),
                "escalation": state.get("escalation"),
                "features": state.get("features"),
                "prev_hash": last["hash"]
            }

            record["hash"] = self._hash(record)
            history.append(record)

            f.seek(0)
            json.dump(history, f, indent=2)

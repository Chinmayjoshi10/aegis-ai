import hashlib
import json
import numpy as np


class ImmuneBrain:
    """
    Enterprise immune system.
    Detects poisoned, adversarial, or unstable data patterns.
    """

    def __init__(self):
        self.baseline_fingerprints = []
        self.quarantine = []

    def fingerprint(self, data):
        blob = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    def extract_metrics(self, data):
        nums = []
        for v in data.values():
            if isinstance(v, (int, float)):
                nums.append(v)
        if not nums:
            return None
        return {
            "mean": float(np.mean(nums)),
            "std": float(np.std(nums)),
            "min": float(np.min(nums)),
            "max": float(np.max(nums))
        }

    def observe(self, data):
        fp = self.fingerprint(data)
        metrics = self.extract_metrics(data)

        # Learn baseline
        if len(self.baseline_fingerprints) < 50:
            self.baseline_fingerprints.append((fp, metrics))
            return {"status": "learning_baseline"}

        # Compare
        known_fps = [f for f, _ in self.baseline_fingerprints]
        if fp not in known_fps:
            return {"status": "unknown_pattern", "risk": 0.7}

        # Statistical sanity
        if metrics:
            means = [m["mean"] for _, m in self.baseline_fingerprints if m]
            if abs(metrics["mean"] - np.mean(means)) > 3 * np.std(means):
                self.quarantine.append(data)
                return {"status": "statistical_poison", "risk": 0.95}

        return {"status": "clean"}

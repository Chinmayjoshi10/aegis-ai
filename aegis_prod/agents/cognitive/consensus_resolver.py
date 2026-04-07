from math import exp

class ConsensusResolver:
    """
    Enterprise-grade truth arbitration & self-correcting belief engine.
    """

    # Initial trust model (self-evolves over time)
    SOURCE_WEIGHTS = {
        "AUTOMATED_SENSOR": 1.0,
        "SYSTEM_LOG": 0.9,
        "HUMAN_REPORT": 0.6,
        "EMAIL": 0.4,
        "UNKNOWN": 0.5
    }

    # Temporal truth decay constant
    LAMBDA = 0.05

    # Conflict detection threshold
    CONFLICT_THRESHOLD = 0.7

    def __init__(self, pg):
        self.pg = pg

    def compute_score(self, fact, state: dict):
        base = self.SOURCE_WEIGHTS.get(fact["source_type"], 0.5) * fact["confidence"]
        clock = state["_clock"]
        age = (clock.now() - fact["ts"]).total_seconds()
        return base * exp(-self.LAMBDA * age)

    def resolve(self, facts, entity, attribute, state: dict):
        """
        Returns: (best_value, best_score)
        """
        bucket = {}

        for f in facts:
            bucket.setdefault(f["value"], []).append(f)

        best_val = None
        best_score = 0
        second_best = 0
        best_fact = None

        for val, group in bucket.items():
            score = sum(self.compute_score(f, state) for f in group) * len(group)

            if score > best_score:
                second_best = best_score
                best_score = score
                best_val = val
                best_fact = group[0]

        # Conflict itself is a risk signal
        if best_score > 0 and (best_score - second_best) > self.CONFLICT_THRESHOLD:
            if hasattr(self.pg, "insert_dict"):
                self.pg.insert_dict(
                    "aegis_drift_history",
                    {
                        "metric_name": f"{entity}.{attribute}",
                        "drift_score": best_score - second_best,
                        "reason": "CONSENSUS_VIOLATION",
                    },
                )
            else:
                self.pg.insert(
                    "aegis_drift_history",
                    metric_name=f"{entity}.{attribute}",
                    drift_score=best_score - second_best,
                    reason="CONSENSUS_VIOLATION",
                )

        # Self-correcting sensors
        for f in facts:
            if f["source_type"] == "AUTOMATED_SENSOR" and f["value"] != best_val:
                if hasattr(self.pg, "insert_dict"):
                    self.pg.insert_dict(
                        "aegis_feedback",
                        {
                            "source_id": f["source_id"],
                            "status": "DEGRADED",
                            "reason": "CONSISTENTLY_OUTVOTED",
                        },
                    )
                else:
                    self.pg.insert(
                        "aegis_feedback",
                        source_id=f["source_id"],
                        status="DEGRADED",
                        reason="CONSISTENTLY_OUTVOTED",
                    )

        return best_val, best_score

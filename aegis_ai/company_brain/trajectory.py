from typing import Dict, List, Any
from collections import defaultdict
import statistics


class TrajectoryEngine:
    """
    Trajectory Engine — Phase A + Phase B.

    Phase A:
    - Lineage key
    - Persistence interpretation
    - Escalation velocity

    Phase B:
    - Reversibility heuristic

    HARD RULES:
    - Never creates insights
    - Never alters confidence
    - Never overrides SystemState
    - Fail-open always
    """

    # -------------------------------------------------
    # PUBLIC ENTRY
    # -------------------------------------------------
    def annotate(
        self,
        *,
        insights: List[Dict[str, Any]],
        insight_history: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:

        if not insights:
            return insights

        history_by_lineage = self._index_history(insight_history)

        for insight in insights:
            lineage_key = self._compute_lineage_key(insight)
            insight["lineage_key"] = lineage_key

            lineage_history = history_by_lineage.get(lineage_key, [])

            persistence = self._interpret_persistence(lineage_history)
            velocity = self._compute_velocity(lineage_history)
            reversibility = self._compute_reversibility(
                lineage_history=lineage_history,
                persistence=persistence,
                velocity=velocity,
            )

            insight["trajectory"] = {
                "persistence": persistence,
                "velocity": velocity,
                "reversibility": reversibility,
            }

        return insights

    # -------------------------------------------------
    # LINEAGE
    # -------------------------------------------------
    def _compute_lineage_key(self, insight: Dict[str, Any]) -> str:
        primitive = insight.get("primitive", "UNKNOWN")
        metrics = insight.get("metrics", [])
        direction = insight.get("direction", "NONE")

        metrics_part = "|".join(sorted(map(str, metrics)))
        return f"{primitive}:{metrics_part}:{direction}"

    # -------------------------------------------------
    # HISTORY INDEX
    # -------------------------------------------------
    def _index_history(
        self,
        history: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:

        buckets = defaultdict(list)

        for past in history:
            key = past.get("lineage_key")
            if not key:
                continue
            buckets[key].append(past)

        return buckets

    # -------------------------------------------------
    # PERSISTENCE INTERPRETATION
    # -------------------------------------------------
    def _interpret_persistence(
        self,
        lineage_history: List[Dict[str, Any]],
    ) -> str:

        if not lineage_history:
            return "INSUFFICIENT_HISTORY"

        confirmations = len(lineage_history)

        if confirmations >= 5:
            return "HIGH"
        if confirmations >= 2:
            return "MEDIUM"
        return "LOW"

    # -------------------------------------------------
    # ESCALATION VELOCITY
    # -------------------------------------------------
    def _compute_velocity(
        self,
        lineage_history: List[Dict[str, Any]],
    ) -> str:

        if len(lineage_history) < 2:
            return "UNKNOWN"

        scores = [
            h.get("signal_score")
            for h in lineage_history
            if isinstance(h.get("signal_score"), (int, float))
        ]

        if len(scores) < 2:
            return "UNKNOWN"

        try:
            deltas = [
                scores[i] - scores[i - 1]
                for i in range(1, len(scores))
            ]

            avg_delta = statistics.mean(deltas)

            if avg_delta > 0.05:
                return "ESCALATING"
            if avg_delta < -0.05:
                return "DEESCALATING"
            return "STABLE"

        except Exception:
            return "UNKNOWN"

    # -------------------------------------------------
    # REVERSIBILITY HEURISTIC (PHASE B)
    # -------------------------------------------------
    def _compute_reversibility(
        self,
        *,
        lineage_history: List[Dict[str, Any]],
        persistence: str,
        velocity: str,
    ) -> str:
        """
        Deterministic reversibility heuristic.

        Intuition:
        - Short-lived + non-escalating signals are easier to reverse
        - Persistent + escalating signals are harder to reverse
        """

        if not lineage_history:
            return "UNKNOWN"

        # Base score (lower = easier to reverse)
        score = 0

        # Persistence impact
        if persistence == "HIGH":
            score += 2
        elif persistence == "MEDIUM":
            score += 1

        # Velocity impact
        if velocity == "ESCALATING":
            score += 2
        elif velocity == "STABLE":
            score += 1

        # Volatility impact
        try:
            scores = [
                h.get("signal_score")
                for h in lineage_history
                if isinstance(h.get("signal_score"), (int, float))
            ]

            if len(scores) >= 3:
                volatility = statistics.pstdev(scores)
                if volatility < 0.05:
                    score += 1
        except Exception:
            pass

        if score <= 1:
            return "HIGH_REVERSIBILITY"
        if score <= 3:
            return "MEDIUM_REVERSIBILITY"
        return "LOW_REVERSIBILITY"

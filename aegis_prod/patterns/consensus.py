from collections import defaultdict
from typing import List, Tuple

from aegis_ai.patterns.signals import PatternSignal


class ConsensusEngine:
    """
    Combines pattern signals from multiple detectors
    and escalates confidence based on agreement.
    """

    def apply(self, signals: List[PatternSignal]) -> List[PatternSignal]:
        if not signals:
            return []

        grouped: dict[Tuple[str, str, str], List[PatternSignal]] = defaultdict(list)

        # Group by (domain, metric, window)
        for s in signals:
            key = (s.domain, s.metric, s.window)
            grouped[key].append(s)

        resolved: List[PatternSignal] = []

        for key, group in grouped.items():
            if len(group) == 1:
                # Only one detector fired → keep as-is
                resolved.append(group[0])
                continue

            # Multiple detectors fired on same metric/window
            models = {s.model for s in group}

            for s in group:
                if len(models) >= 2:
                    s.confidence = "HIGH"
                resolved.append(s)

        return resolved

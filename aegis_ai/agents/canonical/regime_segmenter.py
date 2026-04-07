from typing import Dict, Any
import numpy as np


class RegimeSegmenter:
    """
    Context-only agent.
    Adds regime labels to intelligence.
    No insights. No ML.
    """

    def run(self, state: Dict[str, Any]) -> None:
        intelligence = state.setdefault("intelligence", {})
        reality = state.get("reality") or state.get("physics")

        if not reality:
            return

        stats = reality.get("stats")
        if not stats:
            return

        # ───────── LOAD REGIME ─────────
        try:
            volume = stats.get("row_count")
            history = stats.get("historical_row_counts")

            if volume is None or not history or len(history) < 5:
                load = "NORMAL"
            else:
                median = np.median(history)
                q1 = np.percentile(history, 25)
                q3 = np.percentile(history, 75)
                iqr = q3 - q1

                if volume < median - 0.5 * iqr:
                    load = "LOW"
                elif volume > median + 0.5 * iqr:
                    load = "HIGH"
                else:
                    load = "NORMAL"
        except Exception:
            load = "NORMAL"

        # ───────── STRESS REGIME ─────────
        stress_flags = 0

        try:
            if stats.get("variance_ratio", 0) > 1.5:
                stress_flags += 1
            if stats.get("outlier_ratio", 0) > 0.08:
                stress_flags += 1
            if stats.get("null_ratio", 0) > 0.1:
                stress_flags += 1
        except Exception:
            pass

        stress = "STRESSED" if stress_flags >= 2 else "NORMAL"

        # ───────── WRITE CONTEXT ONLY ─────────
        intelligence["regime"] = {
            "load": load,
            "stress": stress,
            "stress_flags": stress_flags,
        }

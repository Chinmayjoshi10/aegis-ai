from typing import List, Dict, Any
import pandas as pd

from aegis_ai.causality.causal_core import TimeCausalGraph
from aegis_ai.causality.transfer_entropy import TransferEntropyEngine


class CausalEngine:

    def __init__(self):
        self.te = TransferEntropyEngine()

    def infer_causality(self, insights: List[Dict[str, Any]]):

        if not insights:
            return {
                "drivers": [],
                "root_causes": [],
                "leading_indicators": []
            }

        df = self._to_dataframe(insights)

        if df.empty:
            return {
                "drivers": [],
                "root_causes": [],
                "leading_indicators": []
            }

        # -------------------------
        # TRANSFER ENTROPY
        # -------------------------
        te_scores = self.te.compute(df)

        drivers = []
        for (src, tgt), score in te_scores.items():
            if score > 0:
                drivers.append(f"{src} → {tgt}")

        # -------------------------
        # TIME GRAPH (NEW)
        # -------------------------
        graph = TimeCausalGraph().with_time_lag(df)
        top_drivers = graph.top_drivers()

        leading = [
            f"{feat} (score={score})"
            for feat, score in top_drivers
        ]

        # -------------------------
        # ROOT CAUSE
        # -------------------------
        root_causes = self._infer_root_causes(insights)

        return {
            "drivers": drivers[:3],
            "root_causes": root_causes[:3],
            "leading_indicators": leading
        }

    # -------------------------
    # HELPERS
    # -------------------------

    def _to_dataframe(self, insights):
        rows = []

        for ins in insights:
            metric = ins.get("metric")
            evidence = ins.get("evidence", {})

            if not metric:
                continue

            value = evidence.get("cusum_peak") or evidence.get("baseline_mean") or 0

            rows.append({metric: value})

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows).fillna(0)

    def _infer_root_causes(self, insights):
        causes = []

        for ins in insights:
            metric = ins.get("metric", "").lower()

            if "price" in metric or "cost" in metric:
                causes.append("pricing")

            elif "traffic" in metric or "visit" in metric:
                causes.append("traffic")

            elif "conversion" in metric or "sales" in metric:
                causes.append("conversion dynamics")

        return list(set(causes))

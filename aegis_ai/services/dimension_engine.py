from typing import List, Dict, Any
from collections import defaultdict


class DimensionEngine:
    """
    Domain-agnostic dimension inference + segment extraction
    Works across finance, sales, HR, ops, marketing
    """

    def extract_dimensions(self, insights: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        """
        Returns:
        {
            "region": {"US": 0.32, "EU": -0.12},
            "product": {"A": 0.21, "B": -0.18}
        }
        """

        dimension_impact = defaultdict(lambda: defaultdict(float))

        for ins in insights:

            evidence = ins.get("evidence", {})
            delta = ins.get("delta", 0)

            # 🔥 CORE IDEA: look for grouped contributions
            contributions = evidence.get("dimension_impact", {})

            if isinstance(contributions, dict):
                for dim, values in contributions.items():

                    if isinstance(values, dict):
                        for val, impact in values.items():
                            dimension_impact[dim][val] += impact

        # normalize
        return {
            dim: dict(vals)
            for dim, vals in dimension_impact.items()
        }

    # -------------------------
    # TOP SEGMENTS
    # -------------------------

    def top_segments(self, dimension_impact: Dict[str, Dict[str, float]], top_k=2):

        top = {}

        for dim, values in dimension_impact.items():
            sorted_vals = sorted(
                values.items(),
                key=lambda x: abs(x[1]),
                reverse=True
            )

            top[dim] = sorted_vals[:top_k]

        return top
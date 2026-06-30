# aegis_ai/core/causal_engine.py

from typing import Dict, List, Any
from collections import defaultdict


# =========================
# UTILS
# =========================

def _group_metrics_by_role(events: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    role_map = defaultdict(list)

    for e in events:
        role = e.get("role", "UNKNOWN")
        metric = e.get("metric", "unknown_metric")

        role_map[role].append(metric)

    return role_map


def _pick_representative(metrics: List[str]) -> str:
    if not metrics:
        return "unknown"
    return metrics[0]  # deterministic (can improve later)


# =========================
# CORE ENGINE
# =========================

def generate_causal_hints(
    pattern_type: str,
    role_scores: Dict[str, float],
    events: List[Dict[str, Any]]
) -> List[str]:

    causes = []

    role_metrics = _group_metrics_by_role(events)

    input_metric = _pick_representative(role_metrics.get("INPUT", []))
    output_metric = _pick_representative(role_metrics.get("OUTPUT", []))
    value_metric = _pick_representative(role_metrics.get("VALUE", []))
    cost_metric = _pick_representative(role_metrics.get("COST", []))
    efficiency_metric = _pick_representative(role_metrics.get("EFFICIENCY", []))

    input_score = role_scores.get("INPUT", 0)
    output_score = role_scores.get("OUTPUT", 0)
    value_score = role_scores.get("VALUE", 0)
    cost_score = role_scores.get("COST", 0)
    efficiency_score = role_scores.get("EFFICIENCY", 0)

    # ------------------------
    # Efficiency Collapse
    # ------------------------
    if pattern_type == "EFFICIENCY_COLLAPSE":

        if input_score > 0 and output_score < 0:
            causes.append(
                f"Increased {input_metric} (input) is not converting into {output_metric} (output)"
            )

        if efficiency_score < 0:
            causes.append(
                f"{efficiency_metric} metrics indicate declining efficiency"
            )

        causes.append("Possible bottleneck in conversion or processing pipeline")

    # ------------------------
    # Demand Collapse
    # ------------------------
    elif pattern_type == "DEMAND_COLLAPSE":

        if output_score < 0 and value_score < 0:
            causes.append(
                f"{output_metric} (output) and {value_metric} (value) are both declining"
            )

        causes.append("Possible decline in customer demand or market conditions")

    # ------------------------
    # Cost Explosion
    # ------------------------
    elif pattern_type == "COST_EXPLOSION":

        if cost_score > 0:
            causes.append(
                f"{cost_metric} (cost) is increasing without proportional output gains"
            )

        causes.append("Possible inefficient budget allocation")

    # ------------------------
    # Efficiency Gain
    # ------------------------
    elif pattern_type == "EFFICIENCY_GAIN":

        if output_score > 0:
            causes.append(
                f"{output_metric} improving despite reduced {input_metric}"
            )

        causes.append("Improved process efficiency or targeting")

    # ------------------------
    # Efficiency Shift
    # ------------------------
    elif pattern_type == "EFFICIENCY_SHIFT":

        direction = "improving" if efficiency_score > 0 else "declining"

        causes.append(
            f"{efficiency_metric} is {direction} significantly"
        )

    return causes
# aegis_ai/core/correlation_engine.py

from typing import List, Dict, Any
from collections import defaultdict


def _build_group_key(event: Dict[str, Any]) -> tuple:
    """
    Build grouping key using hierarchical context
    """

    role = event.get("role", "UNKNOWN")
    impact = event.get("impact", "NEUTRAL")

    # Domain awareness (NEW)
    domain = event.get("domain", "GLOBAL")
    subdomain = event.get("subdomain", None)

    if subdomain:
        return (role, impact, domain, subdomain)

    return (role, impact, domain)


def group_correlated_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Domain-aware grouping engine

    Prevents:
    - cross-domain signal merging
    - false aggregation across systems
    """

    grouped = defaultdict(list)

    for e in events:
        key = _build_group_key(e)
        grouped[key].append(e)

    merged_events = []

    for key, group in grouped.items():

        role = group[0].get("role")
        impact = group[0].get("impact")
        domain = group[0].get("domain", "GLOBAL")
        subdomain = group[0].get("subdomain")

        total_weight = sum(e.get("weight", 0) for e in group)

        avg_confidence = sum(e.get("confidence", 0) for e in group) / len(group)

        max_magnitude = max(abs(e.get("magnitude_pct", 0)) for e in group)

        representative = group[0]

        merged_events.append({
            "metric": f"{role}_GROUP",
            "role": role,
            "impact": impact,
            "domain": domain,
            "subdomain": subdomain,
            "direction": representative.get("direction"),
            "confidence": round(avg_confidence, 4),
            "magnitude_pct": max_magnitude,
            "severity": representative.get("severity"),
            "weight": round(total_weight, 4),
            "group_size": len(group),
        })

    return merged_events
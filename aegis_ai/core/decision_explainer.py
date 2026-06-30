from typing import List, Dict, Any


def generate_decision_cards(decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

    cards = []

    for d in decisions:

        cards.append({
            "title": d["type"].replace("_", " ").title(),
            "summary": d["decision"],
            "confidence": d["confidence"],
            "impact": d["impact"],
            "signals": d.get("signals", []),
            "action": _suggest_action(d["type"])
        })

    return cards


def _suggest_action(decision_type: str) -> str:

    mapping = {
        "EFFICIENCY_GAIN": "Scale current strategy and reallocate budget to high-performing areas",
        "DEMAND_DECLINE": "Investigate funnel drop-offs and improve acquisition channels",
        "PRICING_SHIFT": "Review pricing strategy and monitor customer response",
        "INVENTORY_SHIFT": "Optimize inventory allocation and reduce supply imbalance",
        "GENERIC_TREND": "Analyze drivers behind metric changes"
    }

    return mapping.get(decision_type, "Review underlying drivers")
from typing import List, Dict, Any


class DecisionExplainer:

    def explain(
        self,
        decisions: List[Dict[str, Any]],
        insights: List[Dict[str, Any]] | None = None,
    ):
        insights = insights or []
        cards = []

        for d in decisions:
            card = {
                "title":       self._title(d),
                "summary":     d.get("decision"),
                "confidence":  d.get("confidence"),
                "impact":      d.get("impact"),
                "priority":    self._priority(d),
                "why":         self._why(d, insights),
                "drivers":     self._drivers(d, insights),
                "root_causes": self._root_causes(d),
                "actions":     self._actions(d),
                "segments":    d.get("segments", []),
                "visualization": d.get("visualization", {}),
                "type":        d.get("type"),
                "validation_status":    d.get("validation_status", "UNVERIFIED"),
                "supporting_metrics":   d.get("supporting_metrics", []),
                "conflicting_metrics":  d.get("conflicting_metrics", []),
                "domain_rules_applied": d.get("domain_rules_applied", []),
            }
            cards.append(card)

        return cards

    # ── Title map covers all real decision types ──────────────────────────

    def _title(self, d):
        mapping = {
            "EFFICIENCY_GAIN":    "Efficiency is Improving",
            "GROWTH_SIGNAL":      "Growth Signal Detected",
            "DEMAND_DECLINE":     "Demand is Declining",
            "PRICING_SHIFT":      "Pricing Shift Detected",
            "FUNNEL_BREAKDOWN":   "Funnel Breakdown Detected",
            "QUALITY_DETERIORATION": "Quality is Deteriorating",
            "INVENTORY_SHIFT":    "Inventory Movement Detected",
            "STRUCTURAL_CHANGE":  "Structural Change Detected",
            "METRIC_ALERT":       "Metric Alert",
            "STABLE":             "System is Stable",
        }
        # Prefer the decision's own title if it has one
        own_title = d.get("title")
        if own_title and own_title not in ("Business Change Detected",):
            return own_title
        return mapping.get(d.get("type"), "Business Change Detected")

    # ── Priority ──────────────────────────────────────────────────────────

    def _priority(self, d):
        try:
            impact = float(d.get("impact", 0) or 0)
        except (ValueError, TypeError):
            impact = 0.0
        if impact >= 0.7:
            return "CRITICAL"
        elif impact >= 0.4:
            return "HIGH"
        elif impact >= 0.2:
            return "MEDIUM"
        return "LOW"

    # ── Why — driven from segment_context on the decision ────────────────

    def _why(self, d, insights):
        explanations = []

        # 1. Segment context attached to the decision itself
        for seg in d.get("segments", []):
            dim   = seg.get("dimension", "")
            val   = seg.get("value", "")
            dev   = seg.get("deviation", 0.0)
            dev_pct = round(abs(dev) * 100)
            direction = "higher" if dev > 0 else "lower"
            if dim and val:
                explanations.append(
                    f"{val} ({dim}) shows {dev_pct}% {direction} deviation from global average"
                )

        # 2. Segment context from raw insights for this decision's metrics
        decision_metrics = {s.lower() for s in d.get("signals", [])}
        for ins in insights:
            m = (ins.get("metric") or "").lower()
            if m not in decision_metrics:
                continue
            for seg in (ins.get("segment_context") or [])[:2]:
                dim   = seg.get("dimension", "")
                val   = seg.get("value", "")
                dev   = seg.get("deviation", 0.0)
                dev_pct = round(abs(dev) * 100)
                direction = "higher" if dev > 0 else "lower"
                label = f"{val} ({dim}) drives {dev_pct}% {direction} movement in {ins.get('metric', m)}"
                if label not in explanations:
                    explanations.append(label)

        # 3. Supporting / conflicting from cross-validation
        for sm in d.get("supporting_metrics", [])[:2]:
            explanations.append(f"{sm} supports this signal")
        for cm in d.get("conflicting_metrics", [])[:2]:
            explanations.append(f"{cm} is moving in the opposite direction")

        if not explanations:
            direction_txt = ""
            for ins in insights:
                m = (ins.get("metric") or "").lower()
                if m in decision_metrics:
                    dir_ = ins.get("direction") or ins.get("subtype") or ""
                    if dir_:
                        direction_txt = f"{ins.get('metric', m)} trend is {dir_.lower()}"
                        break
            explanations.append(direction_txt or "Signal detected via statistical analysis")

        return explanations[:5]

    # ── Drivers — metric-level signal direction summary ───────────────────

    def _drivers(self, d, insights):
        # Prefer pre-built drivers from cross-validator (segment-derived)
        pre_built = d.get("drivers") or []
        if pre_built:
            return pre_built[:3]
        # Fallback: derive from insight directions
        drivers = []
        decision_metrics = {s.lower() for s in d.get("signals", [])}
        for ins in insights:
            m = (ins.get("metric") or "").lower()
            if m not in decision_metrics:
                continue
            dir_ = ins.get("direction") or ins.get("subtype") or ""
            if dir_:
                drivers.append(f"{ins.get('metric', m)} ({dir_.lower()})")
        return drivers[:3]

    # ── Root causes from domain rules ─────────────────────────────────────

    def _root_causes(self, d):
        return d.get("domain_rules_applied", [])

    # ── Actions cover all real decision types ─────────────────────────────

    def _actions(self, d):
        t = d.get("type")

        if t == "EFFICIENCY_GAIN":
            return ["Scale efficient segments", "Increase allocation to top drivers"]
        if t == "GROWTH_SIGNAL":
            return ["Double down on high-growth segments", "Investigate growth drivers"]
        if t == "DEMAND_DECLINE":
            return ["Investigate declining categories", "Adjust inventory and pricing"]
        if t == "PRICING_SHIFT":
            return ["Review pricing strategy", "Benchmark against market rates"]
        if t == "FUNNEL_BREAKDOWN":
            return ["Audit each funnel stage", "Identify highest drop-off point"]
        if t == "QUALITY_DETERIORATION":
            return ["Initiate quality review process", "Isolate affected segments"]
        if t == "INVENTORY_SHIFT":
            return ["Rebalance stock levels", "Review demand forecasts"]
        if t == "STRUCTURAL_CHANGE":
            return ["Investigate root cause", "Monitor affected metric closely"]
        if t == "METRIC_ALERT":
            return ["Review metric trend", "Assess whether intervention is required"]
        if t == "STABLE":
            return ["Continue monitoring", "Review on next data upload"]

        return ["Investigate drivers", "Monitor closely"]

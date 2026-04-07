class Normalizer:
    """
    Converts raw enterprise events into semantic physics-ready signals.
    """

    DOMAIN_MAP = {
        "sales": ["leads", "lost_leads"],
        "ops": ["throughput", "backlog"],
        "logistics": ["delay", "blockage"],
        "finance": ["cash", "expenses"],
        "hr": ["attrition"]
    }

    SEMANTIC_MAP = {
        "leads": ("sales", "flow_rate"),
        "lost_leads": ("sales", "leakage_rate"),
        "throughput": ("ops", "throughput"),
        "backlog": ("ops", "fatigue"),
        "delay": ("logistics", "blockage"),
        "expenses": ("finance", "burn_rate"),
        "cash": ("finance", "cash_reserve"),
        "attrition": ("hr", "burnout_pressure")
    }

    def normalize(self, clean_payload: dict):
        events = []

        for k, v in clean_payload.items():
            if k in self.SEMANTIC_MAP:
                domain, metric = self.SEMANTIC_MAP[k]
                events.append({
                    "domain": domain,
                    "metric": metric,
                    "value": float(v)
                })

        return events

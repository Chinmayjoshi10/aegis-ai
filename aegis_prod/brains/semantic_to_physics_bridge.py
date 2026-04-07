class SemanticToPhysicsBridge:
    """
    Converts semantic enterprise facts into normalized physics pressure fields.
    """

    SEMANTIC_MAP = {
        "Sales": {
            "leads": ("sales", "flow_rate", 0.01),
            "lost leads": ("sales", "leakage_rate", 0.01)
        },
        "Ops": {
            "throughput": ("ops", "throughput", 0.01),
            "backlog": ("ops", "fatigue", 0.01)
        },
        "Logistics": {
            "delay": ("logistics", "blockage", 0.1)
        },
        "Finance": {
            "expenses": ("finance", "burn_rate", 0.01),
            "cash": ("finance", "cash_reserve", 0.001)
        },
        "HR": {
            "attrition": ("hr", "burnout_pressure", 5.0)
        }
    }

    def run(self, state):
        physics = state.setdefault("physics", {})
        facts = state.get("semantic_facts", [])

        for f in facts:
            entity = f["entity"]
            attr = f["attribute"].lower()
            try:
                val = float(f["value"])
            except:
                continue

            if entity in self.SEMANTIC_MAP and attr in self.SEMANTIC_MAP[entity]:
                domain, field, scale = self.SEMANTIC_MAP[entity][attr]
                physics.setdefault(domain, {})

                # Accumulate instead of overwrite (physics memory)
                prev = physics[domain].get(field, 0.0)
                physics[domain][field] = prev + (val * scale)

        return state

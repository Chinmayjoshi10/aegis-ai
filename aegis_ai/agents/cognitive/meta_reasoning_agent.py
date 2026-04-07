class MetaReasoningAgent:
    """
    Cognitive supervisor that fuses all brains into decisions.
    """

    def __init__(self, pg):
        self.pg = pg

    def reason(self, entity, attribute):
        facts = self.pg.fetch_all("semantic_facts", entity=entity, attribute=attribute, is_active=True)
        intents = self.pg.fetch_all("cognitive_intents")
        drifts = self.pg.fetch_all("aegis_drift_history")
        forecasts = self.pg.fetch_all("aegis_forecasts")

        planned = any(i["intent_type"] == "maintenance" for i in intents)
        risky = any(d["reason"] == "CONSENSUS_VIOLATION" for d in drifts)

        if planned:
            return {
                "status": "PLANNED_EVENT",
                "action": "SUPPRESS_ALERT",
                "message": f"{entity}.{attribute} change is due to planned maintenance."
            }

        if risky:
            return {
                "status": "RISK",
                "action": "ESCALATE",
                "message": f"{entity}.{attribute} shows conflicting reality. Investigate immediately."
            }

        return {
            "status": "NORMAL",
            "action": "MONITOR",
            "message": f"{entity}.{attribute} is stable."
        }

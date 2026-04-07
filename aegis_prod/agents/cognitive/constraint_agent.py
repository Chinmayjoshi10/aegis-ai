class ConstraintAgent:
    """
    Reality firewall — blocks hallucinated or impossible facts.
    Enforces aegis_semantic_contracts.
    """

    def __init__(self, pg):
        self.pg = pg

    def validate_fact(self, fact: dict):
        contract = self.pg.fetch_one(
            "aegis_semantic_contracts",
            attribute=fact["attribute"]
        )

        if not contract:
            return True, None

        try:
            value = float(fact["value"])
            min_v = float(contract["min_value"])
            max_v = float(contract["max_value"])
        except:
            return True, None

        if value < min_v or value > max_v:
            return False, {
                "reason": "CONTRACT_VIOLATION",
                "contract": contract,
                "fact": fact
            }

        return True, None

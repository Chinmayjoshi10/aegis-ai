from aegis_ai.domains.manufacturing_adapter import ManufacturingAdapter
from aegis_ai.domains.finance_adapter import FinanceComplianceAdapter


class DomainRouterAgent:
    """
    Routes raw data through the correct domain adapter.
    """

    def __init__(self):
        self.adapters = {
            "manufacturing": ManufacturingAdapter(),
            "finance": FinanceComplianceAdapter()
        }

    def run(self, state: dict):
        domain = state.get("domain")
        df = state.get("data")

        if domain in self.adapters:
            state["data"] = self.adapters[domain].adapt(df)

        return state

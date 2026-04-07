from aegis_ai.physics.sales_physics_brain import SalesPhysicsBrain
from aegis_ai.physics.ops_physics_brain import OpsPhysicsBrain
from aegis_ai.physics.logistics_physics_brain import LogisticsPhysicsBrain
from aegis_ai.physics.finance_physics_brain import FinancePhysicsBrain
from aegis_ai.physics.hr_physics_brain import HRPhysicsBrain


class PhysicsRouterAgent:

    def __init__(self):
        self.sales = SalesPhysicsBrain()
        self.ops = OpsPhysicsBrain()
        self.logistics = LogisticsPhysicsBrain()
        self.finance = FinancePhysicsBrain()
        self.hr = HRPhysicsBrain()

    def run(self, state: dict):
        if "physics" not in state:
            state["physics"] = {}

        features = state.get("features", {})

        if "sales" in features:
            state = self.sales.run(state)
        if "ops" in features:
            state = self.ops.run(state)
        if "logistics" in features:
            state = self.logistics.run(state)
        if "finance" in features:
            state = self.finance.run(state)
        if "hr" in features:
            state = self.hr.run(state)

        return state

from datetime import datetime, timedelta
from aegis_ai.stability.action_catalog import ACTION_CATALOG

class HomeostasisController:
    """
    Closed-loop self-healing controller with:
    - Proportional servo actions (risk-scaled)
    - Action synergy governance (finance pool guard)
    - Phase Lock escalation
    """

    def __init__(self):
        self.cooldowns = {}              # action -> next_allowed_datetime
        self.phase_locked = False       # Phase Lock switch

    def _can_fire(self, action):
        now = datetime.utcnow()
        return action not in self.cooldowns or now >= self.cooldowns[action]

    def _arm_cooldown(self, action):
        cd = ACTION_CATALOG[action].get("cooldown_days", 7)
        self.cooldowns[action] = datetime.utcnow() + timedelta(days=cd)

    def _servo_scale(self, global_risk):
        """
        Map global_risk [0.7..1.0] -> scale [0..1]
        Below 0.7 -> 0 (no act), at 1.0 -> 1 (max act)
        """
        if global_risk < 0.7:
            return 0.0
        return min(1.0, (global_risk - 0.7) / 0.3)

    def _blend_effect(self, base, maxe, scale):
        # Linear blend between base and max by scale
        eff = {}
        for k in base:
            eff[k] = base[k] + (maxe[k] - base[k]) * scale
        return eff

    def _finance_pool_guard(self, state, planned_actions):
        """
        Ensure cumulative healing cost does not exceed 20% of remaining cash runway.
        If exceeded, choose the single most effective action.
        """
        P = state["physics"]
        finance = P["finance"]

        # Estimate available pool: 20% of remaining cash reserve
        pool = 0.20 * finance.get("cash_reserve", 0)

        def est_cost(action):
            spec = ACTION_CATALOG[action]
            if "cost_domain" in spec:
                # approximate daily burn impact on cash
                burn = finance.get("burn_rate", 0)
                return abs(burn * spec["cost_effect"].get("burn_rate", 0))
            return 0

        costs = {a: est_cost(a) for a in planned_actions}
        total = sum(costs.values())

        if total <= pool:
            return planned_actions  # OK

        # Pick the single most effective action (highest expected delta on failure_probability)
        # Heuristic: choose the action with highest max_effect magnitude
        def efficacy(a):
            spec = ACTION_CATALOG[a]
            return max(abs(v) for v in spec["max_effect"].values())

        best = max(planned_actions, key=efficacy)
        return [best]

    def run(self, state: dict):
        if self.phase_locked:
            state["actions"] = []
            state["healing_log"] = [{"action": "PHASE_LOCK_ACTIVE", "timestamp": datetime.utcnow().isoformat()}]
            return state

        P = state.get("physics", {})
        actions = []
        log = []

        global_risk = P.get("global_collapse_risk", 0)
        scale = self._servo_scale(global_risk)
        if scale == 0:
            state["actions"] = []
            state["healing_log"] = []
            return state

        # Candidate actions by stressed organs
        if P["ops"]["failure_probability"] > 0.6 and self._can_fire("increase_ops_capacity"):
            actions.append("increase_ops_capacity")
        if P["logistics"]["failure_probability"] > 0.6 and self._can_fire("prioritize_logistics_clearance"):
            actions.append("prioritize_logistics_clearance")
        if P["finance"]["fragility"] > 1.2 and self._can_fire("freeze_nonessential_spend"):
            actions.append("freeze_nonessential_spend")
        if P["hr"]["failure_probability"] > 0.6 and self._can_fire("hire_critical_roles"):
            actions.append("hire_critical_roles")
        if P["ops"]["failure_probability"] > 0.7 and self._can_fire("throttle_sales_campaigns"):
            actions.append("throttle_sales_campaigns")

        # Synergy governance (finance pool guard)
        actions = self._finance_pool_guard(state, actions)

        # Apply proportional effects
        for a in actions:
            spec = ACTION_CATALOG[a]
            dom = spec["domain"]
            eff = self._blend_effect(spec["base_effect"], spec["max_effect"], scale)

            for k, v in eff.items():
                if k in P[dom]:
                    P[dom][k] *= (1 + v)

            # Apply costs (also proportional)
            if "cost_domain" in spec:
                cdom = spec["cost_domain"]
                for k, v in spec["cost_effect"].items():
                    if k in P[cdom]:
                        P[cdom][k] *= (1 + v * scale)

            self._arm_cooldown(a)
            log.append({"action": a, "scale": round(scale, 3), "timestamp": datetime.utcnow().isoformat()})

        state["actions"] = actions
        state["healing_log"] = log
        return state

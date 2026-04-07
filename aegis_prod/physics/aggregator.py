# aegis_ai/physics/aggregator.py


class PhysicsCoupler:
    """
    Global Enterprise Physics Coupler.

    Pure computation layer.
    No persistence.
    No I/O.
    Deterministic.
    """

    BASE_FAILURE = {
        "sales": 0.05,
        "ops": 0.10,
        "logistics": 0.08,
        "finance": 0.20,
        "hr": 0.05,
    }

    BLACKOUT_PENALTY = 0.35

    def run(self, state: dict) -> dict:
        """
        Computes global collapse gravity.

        Expects:
            state["physics"]
            state["blackout_flags"] (optional dict[str, bool])
            state["ingestion_confidence"] (optional float)
        """

        physics = state.setdefault("physics", {})
        blackout_flags = state.get("blackout_flags", {})

        # Ensure organs exist
        for organ, base in self.BASE_FAILURE.items():
            physics.setdefault(organ, {})
            physics[organ].setdefault("failure_probability", base)

        # Base gravity calculation
        gravity = 1.0
        for organ in self.BASE_FAILURE:
            failure_prob = physics[organ]["failure_probability"]
            gravity *= (1 + failure_prob)

        # Sensory blackout reflex (pure input-driven)
        blackout_multiplier = 1.0
        for organ in self.BASE_FAILURE:
            if blackout_flags.get(organ, False):
                blackout_multiplier += self.BLACKOUT_PENALTY

        gravity *= blackout_multiplier

        # Reality confidence dampening
        gravity *= state.get("ingestion_confidence", 1.0)

        state["global_collapse_risk"] = round(gravity, 4)

        # Snapshot continuity
        state["last_physics_snapshot"] = {
            organ: physics[organ]["failure_probability"]
            for organ in self.BASE_FAILURE
        }

        return state
import copy
import time


class SelfRepairBrain:
    """
    Keeps golden snapshots of healthy cognition
    and automatically rolls back on corruption.
    """

    def __init__(self):
        self.last_good_snapshot = None
        self.last_snapshot_time = None

    def snapshot(self, state: dict):
        # store a deep copy of healthy cognition
        self.last_good_snapshot = copy.deepcopy(state)
        self.last_snapshot_time = time.time()

    def is_corrupted(self, state: dict):
        # corruption heuristics
        if state.get("agent_failure"):
            return True
        if state.get("immune_block"):
            return True
        if state.get("guardrail_block"):
            return True
        return False

    def rollback(self, state: dict):
        if self.last_good_snapshot:
            print("🧬 SELF-REPAIR: Rolling back to last safe snapshot")
            restored = copy.deepcopy(self.last_good_snapshot)
            restored["self_repair"] = {
                "action": "rollback",
                "restored_from": self.last_snapshot_time,
            }
            return restored
        return state

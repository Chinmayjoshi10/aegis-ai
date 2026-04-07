class PolicyOptimizerBrain:
    """Simple policy optimizer brain used by tests and the policy agent.

    For now, selects the most frequent historical escalation `level` observed in
    the provided `history`. Returns "NO_CHANGE" when history is empty or no
    valid escalation levels are found.
    """

    def optimize(self, history):
        if not history or not isinstance(history, list):
            return "NO_CHANGE"

        counts = {}
        for entry in history:
            if not isinstance(entry, dict):
                continue
            level = None
            try:
                level = entry.get("escalation", {}) and entry.get("escalation", {}).get("level")
            except Exception:
                level = None
            if level:
                counts[level] = counts.get(level, 0) + 1

        if not counts:
            return "NO_CHANGE"

        # Return most common level (tie-breaker: lexical order)
        return max(sorted(counts.items(), key=lambda x: x[0]), key=lambda x: x[1])[0]

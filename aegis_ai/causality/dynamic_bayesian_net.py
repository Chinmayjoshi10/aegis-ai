class TimeCausalGraph:
    """Minimal TimeCausalGraph shim used for downstream_centrality checks."""

    def __init__(self, base_graph=None):
        self.base_graph = base_graph or {}

    def with_time_lag(self, df):
        # Return self for chaining in the calling code
        return self

    def downstream_centrality(self, feature_name: str) -> float:
        # Default neutral centrality
        return 0.0

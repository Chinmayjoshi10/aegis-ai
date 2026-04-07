from aegis_ai.brains.column_profiler_brain import ColumnProfilerBrain
from aegis_ai.brains.semantic_suggestion_brain import SemanticSuggestionBrain

class DiscoveryAgent:
    """
    Generates semantic onboarding contracts.
    """

    def __init__(self):
        self.profiler = ColumnProfilerBrain()
        self.suggester = SemanticSuggestionBrain()

    def run(self, state: dict):
        df = state["data"]
        profiles = self.profiler.profile(df)
        state["column_profiles"] = profiles
        state["semantic_contract"] = self.suggester.suggest(profiles)
        return state

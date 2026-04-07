class SemanticSuggestionBrain:
    """
    Produces weighted semantic role inferences with confidence scores.
    """

    def suggest(self, profiles: dict):
        contract = {}

        for col, p in profiles.items():
            scores = {}

            # Weight rules
            if p.get("semantic_hint") == "temporal":
                scores["time_index"] = 0.95

            if p.get("matches_email"):
                scores["user_identifier"] = 0.95

            if p.get("semantic_hint") == "numeric":
                scores["process_signal"] = 0.6
                if p["unique_ratio"] > 0.98:
                    scores["identifier"] = 0.9
                if p["unique_count"] <= 10:
                    scores["categorical_attribute"] = 0.7

            if p.get("avg_length", 0) > 30:
                scores["free_text"] = 0.85

            if not scores:
                scores["categorical_attribute"] = 0.4

            best = max(scores, key=scores.get)

            contract[col] = {
                "role": best,
                "confidence": round(scores[best], 3),
                "alternatives": scores
            }

        return contract

import numpy as np
from aegis_ai.memory.shadow_baseline_store import ShadowBaselineStore
from aegis_ai.memory.baseline_model_store import BaselineModelStore
from aegis_ai.agents.cognitive.consensus_resolver import ConsensusResolver
from aegis_ai.agents.cognitive.meta_reasoning_agent import MetaReasoningAgent

class RiskBrainAgent:
    """
    Shadow-anchored risk analyzer.
    Now augmented with Phase-6 semantic truth & intent reasoning.
    """

    def __init__(self):
        self.shadow = ShadowBaselineStore()
        self.baseline_store = BaselineModelStore()

    def run(self, state: dict):
        tenant = state.get("tenant") or state.get("domain") or "default"

        # Load immutable shadow reality
        raw_df = self.shadow.load(tenant)

        # Load baseline envelope
        baseline_model = self.baseline_store.load(tenant)
        if baseline_model is None:
            state["risk"] = {"risk_state": "NORMAL", "risk_score": 0.0, "risk_factors": []}
            state["risk_reason"] = "Baseline warming"
            state.setdefault("intelligence", {})
            state["intelligence"]["risk"] = state["risk"]
            return state

        features = raw_df.select_dtypes(include="number")
        if "target" in features.columns:
            features = features.drop(columns=["target"])

        if features.empty:
            state["risk"] = {"risk_state": "NORMAL", "risk_score": 0.0, "risk_factors": []}
            state["risk_reason"] = "No numeric features"
            state.setdefault("intelligence", {})
            state["intelligence"]["risk"] = state["risk"]
            return state

        scores = baseline_model.decision_function(features)
        risk_score = float(np.clip(-scores.mean(), 0, 1))

        # Map to human-readable state
        if risk_score > 0.8:
            risk_state = "CRITICAL"
        elif risk_score > 0.6:
            risk_state = "HIGH"
        elif risk_score > 0.4:
            risk_state = "ELEVATED"
        else:
            risk_state = "NORMAL"

        state["baseline_score"] = float(scores.mean())
        state["risk"] = {"risk_state": risk_state, "risk_score": risk_score, "risk_factors": list(features.columns)}
        state["risk_reason"] = "Envelope deviation"

        state.setdefault("intelligence", {})
        state["intelligence"]["risk"] = state["risk"]

        # 🧠 Phase-6 Semantic Fusion Layer
        pg = state.get("pg")
        facts = pg.fetch_all("semantic_facts", is_active=True) if pg else None
        if facts:
            truth, _ = ConsensusResolver(pg).resolve(facts, "Plant", "temperature")
            state["resolved_truth"] = truth
            state["meta_decision"] = MetaReasoningAgent(pg).reason("Plant", "temperature")

        return state

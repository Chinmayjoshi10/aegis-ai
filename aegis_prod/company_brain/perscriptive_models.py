from typing import Optional, Dict, Any
import logging
import numpy as np

try:
    import shap
except Exception:
    shap = None  # fail-open

from aegis_ai.company_brain.impact_models import ImpactAnalysis

logger = logging.getLogger(__name__)

# -------------------------
# SHAP controls
# -------------------------

MAX_FEATURES_FOR_SHAP = 30
DIRECTION_MISMATCH_PENALTY = 0.25
INSTABILITY_PENALTY = 0.30


def apply_shap_validation(
    impact: ImpactAnalysis,
) -> ImpactAnalysis:
    """
    Phase 2C.3 — SHAP Attribution & Confidence Calibration

    Mutates ImpactAnalysis safely and returns it.
    Fail-open by design.
    """

    if shap is None:
        return impact

    meta: Dict[str, Any] = impact.metadata or {}
    model = meta.get("_model")
    X = meta.get("_X")
    feature_names = meta.get("feature_names")

    if model is None or X is None or not feature_names:
        return _cleanup(impact)

    if len(feature_names) > MAX_FEATURES_FOR_SHAP:
        return _cleanup(impact)

    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)

        # Mean absolute SHAP per feature
        mean_abs = np.mean(np.abs(shap_values), axis=0)
        total = np.sum(mean_abs)

        shap_strengths = {
            feature_names[i]: mean_abs[i] / total if total > 0 else 0.0
            for i in range(len(feature_names))
        }

        # Direction consistency check
        mismatch = 0
        for c in impact.contributors:
            relevant = [
                v for k, v in shap_strengths.items()
                if k.startswith(c.metric)
            ]
            if not relevant:
                continue

            shap_dir = np.sign(np.mean(relevant))
            if (
                (shap_dir > 0 and c.direction == "negative")
                or (shap_dir < 0 and c.direction == "positive")
            ):
                mismatch += 1

        if mismatch > 0:
            impact.global_confidence *= (1.0 - DIRECTION_MISMATCH_PENALTY)

        # Stability check
        shap_var = np.var(shap_values)
        if shap_var > 0.05:
            impact.global_confidence *= (1.0 - INSTABILITY_PENALTY)

        impact.global_confidence = max(0.0, min(impact.global_confidence, 1.0))

        impact.metadata["shap"] = {
            "direction_mismatches": mismatch,
            "shap_variance": float(shap_var),
        }

    except Exception as e:
        logger.exception("SHAP validation failed (non-blocking): %s", e)

    return _cleanup(impact)


def _cleanup(impact: ImpactAnalysis) -> ImpactAnalysis:
    """
    Remove internal-only metadata before persistence / UI.
    """
    if impact.metadata:
        impact.metadata.pop("_model", None)
        impact.metadata.pop("_X", None)
    return impact

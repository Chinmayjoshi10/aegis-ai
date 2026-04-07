from enum import Enum
from typing import List, Dict, Optional


class SystemState(str, Enum):
    """
    Epistemic state of the AEGIS system for a given execution.

    OBSERVATION:
        - Insufficient information to form structural insights
        - Typically due to low data volume (MIU not met)

    SILENT:
        - System understands the data
        - No insight meets the confidence threshold
        - OR insights are regime-local with no structural contrast
        - Silence is intentional and correct

    INSIGHTFUL:
        - One or more insights meet the confidence threshold
        - System is authorized to speak
    """

    OBSERVATION = "OBSERVATION"
    SILENT = "SILENT"
    INSIGHTFUL = "INSIGHTFUL"


def resolve_system_state(
    *,
    row_count: int,
    insights: List[Dict],
    miu_threshold: int = 1000,
    confidence_threshold: float = 0.7,
    regime_history: Optional[List[Dict]] = None,   # ✅ NEW, OPTIONAL
) -> SystemState:
    """
    Resolve the epistemic state of AEGIS.

    SINGLE SOURCE OF TRUTH.

    LOCKED RULES (UNCHANGED):
    1. If MIU not met -> OBSERVATION
    2. If MIU met and no insight >= confidence -> SILENT
    3. If at least one insight >= confidence -> INSIGHTFUL

    SAFE EXTENSION:
    - If insights are regime-local AND no cross-regime contrast exists,
      system is allowed to remain SILENT.
    """

    # ---------------------------------------------------------
    # RULE 1 — Minimum Information Unit (Hard Gate)
    # ---------------------------------------------------------
    if row_count < miu_threshold:
        return SystemState.OBSERVATION

    # ---------------------------------------------------------
    # RULE 2 — Identify defensible insights
    # ---------------------------------------------------------
    defensible_insights = []

    for insight in insights:
        if not isinstance(insight, dict):
            continue

        confidence = insight.get("confidence")

        if isinstance(confidence, (int, float)) and confidence >= confidence_threshold:
            defensible_insights.append(insight)

    if not defensible_insights:
        return SystemState.SILENT

    # ---------------------------------------------------------
    # SAFE REGIME SUPPRESSION (ADDITIVE, OPTIONAL)
    # ---------------------------------------------------------
    if regime_history:
        try:
            regimes_seen = set()

            for entry in regime_history:
                regime = entry.get("regime")
                if isinstance(regime, dict):
                    key = f"{regime.get('load')}|{regime.get('stress')}"
                    regimes_seen.add(key)

            # If insights exist but only under ONE regime,
            # structural contrast is insufficient → silence allowed
            if len(regimes_seen) < 2:
                return SystemState.SILENT

        except Exception:
            # Fail-open: never block speech if logic fails
            pass

    # ---------------------------------------------------------
    # RULE 3 — Authorized to speak
    # ---------------------------------------------------------
    return SystemState.INSIGHTFUL

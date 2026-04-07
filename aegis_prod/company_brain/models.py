from dataclasses import dataclass, asdict
from typing import Dict, List, Literal, Any, Optional
import uuid
import time


# -------------------------
# Canonical enums
# -------------------------

InsightType = Literal["anomaly", "drift", "risk", "stability"]
Severity = Literal["low", "medium", "high"]
Direction = Literal["positive", "negative", "unknown"]
Magnitude = Literal["small", "moderate", "large"]


# -------------------------
# Core structures
# -------------------------

@dataclass(frozen=True)
class Impact:
    """
    Business impact descriptor.
    No prose allowed.
    """
    metrics: List[str]
    direction: Direction
    magnitude: Magnitude


@dataclass(frozen=True)
class Evidence:
    """
    Grounding evidence.
    Every insight MUST link back to system facts.
    """
    reality_metrics: Dict[str, Any]
    pattern_signals: List[Dict[str, Any]]
    drift: Optional[Dict[str, Any]]


@dataclass
class CompanyInsight:
    """
    Canonical Phase-2 insight object.
    This is the spine of AEGIS cognition.
    """
    id: str
    type: InsightType
    summary: str
    severity: Severity
    confidence: float
    impact: Impact
    evidence: Evidence
    recommended_attention: bool
    created_at: float

    # -------------------------
    # Validation guardrails
    # -------------------------
    def validate(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

        if self.type != "stability":
            if not self.impact.metrics:
                raise ValueError("non-stability insights must reference metrics")

        if not (
            self.evidence.pattern_signals
            or self.evidence.drift
            or self.type == "stability"
        ):
            raise ValueError("insight must be grounded in evidence")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return asdict(self)


# -------------------------
# Factory helpers
# -------------------------

def generate_insight_id(prefix: str) -> str:
    return f"{prefix}::{uuid.uuid4().hex[:12]}"


def now_ts() -> float:
    return time.time()

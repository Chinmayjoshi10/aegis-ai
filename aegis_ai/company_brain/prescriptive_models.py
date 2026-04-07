"""Type-only models for Phase 2D prescriptive outputs."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class PrescriptiveSignal:
    """A ranked, explainable recommendation signal derived from insights."""

    insight_id: str
    priority_score: float = 0.0
    urgency: float = 0.0
    actionability_likelihood: float = 0.0
    confidence: float = 0.0
    rationale: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "priority_score": float(self.priority_score),
            "urgency": float(self.urgency),
            "actionability_likelihood": float(self.actionability_likelihood),
            "confidence": float(self.confidence),
            "rationale": self.rationale or {},
        }


__all__ = ["PrescriptiveSignal"]
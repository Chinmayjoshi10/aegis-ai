"""Internal type-only models for Phase 2 impact analysis.

This module exists to provide stable, import-safe dataclasses used by
`aegis_ai.company_brain.xgboost_engine` and downstream validators.

Design constraints:
- No business logic.
- No ML code.
- Conservative defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ImpactContributor:
    """A single candidate metric contributing to a target metric's movement."""

    metric: str
    direction: str = "unknown"  # expected: "positive" | "negative" | "unknown"
    strength: float = 0.0  # normalized [0, 1]
    confidence: float = 0.0  # normalized [0, 1]
    lag: Optional[int] = None


@dataclass
class ImpactAnalysis:
    """Impact analysis result for a single target metric."""

    target_metric: str
    contributors: List[ImpactContributor] = field(default_factory=list)
    model_type: str = "unknown"
    model_version: str = "unknown"
    global_confidence: float = 0.0  # normalized [0, 1]
    metadata: Dict[str, Any] = field(default_factory=dict)


__all__ = [
    "ImpactAnalysis",
    "ImpactContributor",
]


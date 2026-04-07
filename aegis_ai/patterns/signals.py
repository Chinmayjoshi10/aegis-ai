from dataclasses import dataclass
from datetime import datetime
from typing import Literal


# --- Controlled vocabularies (do NOT expand casually) ---

SignalType = Literal[
    "POINT_ANOMALY",      # sudden spike / drop
    "SEQUENCE_ANOMALY",   # unusual temporal pattern
]

ConfidenceLevel = Literal[
    "LOW",      # early / cold start / weak evidence
    "MEDIUM",   # repeated or moderate signal
    "HIGH",     # persistent, strong, well-supported
]


@dataclass
class PatternSignal:
    """
    Atomic pattern-level observation detected by AEGIS.

    This is NOT an insight.
    This is NOT a prediction.
    This is a raw signal to be interpreted by the Company Brain.
    """

    tenant_id: str
    domain: str                    # sales / finance / ops / logistics
    metric: str                    # column / metric name

    signal_type: SignalType
    strength: float                # normalized: 0.0 – 1.0
    confidence: ConfidenceLevel

    window: str                    # e.g. "last_7_days", "last_30_points"
    detected_at: datetime

    # Optional metadata for traceability (safe to extend later)
    model: str | None = None       # "isolation_forest", "tcn"
    version: str | None = None     # model version or hash

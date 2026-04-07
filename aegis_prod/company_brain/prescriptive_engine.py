"""Compatibility shim for Phase 2D prescriptive engine.

The codebase contains [`aegis_ai.company_brain.perscriptive_engine.generate_prescriptive_signals()`](aegis_ai/company_brain/perscriptive_engine.py:9)
but the orchestrator imports `prescriptive_engine` (note the spelling).

This module re-exports the existing implementation to keep behavior unchanged
while fixing imports so the API server can boot.
"""

from __future__ import annotations

from aegis_ai.company_brain.perscriptive_engine import generate_prescriptive_signals


__all__ = [
    "generate_prescriptive_signals",
]


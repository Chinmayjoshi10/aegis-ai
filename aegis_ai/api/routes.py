# aegis_ai/api/routes.py
# Universal Edition — integrates DatasetProfiler, SegmentEngine,
# DecisionValidator, composite timestamps, collision guard.

import logging
import math
from io import BytesIO
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile

from aegis_ai.db.session import SessionLocal
from aegis_ai.sanitizer.data_sanitizer import DataSanitizer
from aegis_ai.sanitizer.semantic_mapper import SemanticMapper, TIMESTAMP_FIELDS
from aegis_ai.sanitizer.quality_gate import QualityGate
from aegis_ai.brains.reality_reader import RealityReader
from aegis_ai.brains.drift_detector import DriftDetector
from aegis_ai.db.baselines.persistence import get_last_baseline, persist_reality_snapshot, get_upload_count
from aegis_ai.spine.event_store import EventStore

# V2 Intelligence
from aegis_ai.company_brain.orchestrator_v2 import run_company_brain_v2
from aegis_ai.services.cognitive_snapshot_service import CognitiveSnapshotService

# Forecast layer
from aegis_ai.company_brain.forecast_integration import attach_forecasts_to_brain_output

# 🔥 Universal components
from aegis_ai.core.dataset_profiler import DatasetProfiler
from aegis_ai.core.decision_pipeline import run_decision_pipeline
from aegis_ai.core.segment_engine import generate_segment_decisions, enrich_signals_with_segments
from aegis_ai.core.cross_validator import cross_validate_decisions
from aegis_ai.core.descriptive_profiler import compute_descriptive_insights
from aegis_ai.core.insight_layer import generate_insights
from aegis_ai.company_brain.decision_synthesizer import (
    deduplicate_semantic_mappings,
    detect_composite_timestamp,
)
from aegis_ai.company_brain.orchestrator_v2 import generate_narrative
from aegis_ai.company_brain.system_state import SystemState

# 🔥 Explainability Layer
from aegis_ai.services.decision_explainer import DecisionExplainer

# Phase 2: Economic Interpretation
from aegis_ai.company_brain.economic_interpreter import enrich_with_economics

# Relative Intelligence Layer — segment vs global comparison
from aegis_ai.core.relative_intelligence import compute_relative_decisions

# Universal Structured Output + Narration + Chatbot
from aegis_ai.core.structured_output import compose_structured_output
from aegis_ai.core.narration import generate_narration, build_narration_meta
from aegis_ai.core.chatbot import answer_question


router = APIRouter()
log = logging.getLogger("aegis_ai.api.routes")

event_store = EventStore()
_profiler   = DatasetProfiler()


# ─────────────────────────────────────────────────────────────────────────────
# JSON SANITIZATION — prevents API crashes from NaN / Infinity
# Applied to EVERY response path (NO_SIGNIFICANT_CHANGE and LIVE).
# ─────────────────────────────────────────────────────────────────────────────

def _sanitize_for_json(obj: Any) -> Any:
    """
    Recursively replace NaN / Infinity with None throughout a response object.
    Also handles numpy scalar types that aren't natively JSON-serializable.
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        cleaned = [_sanitize_for_json(v) for v in obj]
        return cleaned if isinstance(obj, list) else tuple(cleaned)
    # numpy scalar types (np.float64, np.int64, etc.) — convert to native Python
    try:
        import numpy as _np
        if isinstance(obj, (_np.floating, float)):
            val = float(obj)
            if math.isnan(val) or math.isinf(val):
                return None
            return val
        if isinstance(obj, _np.integer):
            return int(obj)
        if isinstance(obj, _np.bool_):
            return bool(obj)
    except ImportError:
        pass
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# DECISION COMPRESSION — merges all insight sources into ranked top 5
# Original lists are preserved in the response; final_decisions is the
# client-facing, compressed, action-first output.
# ─────────────────────────────────────────────────────────────────────────────

# Priority ranking by decision/insight type (lower = more important)
_TYPE_RANK: dict[str, int] = {
    # Global structural decisions (highest priority)
    "REGIME_SHIFT":         0,
    "EFFICIENCY_GAIN":      1,
    "DEMAND_DECLINE":       1,
    "QUALITY_DETERIORATION":1,
    "FUNNEL_BREAKDOWN":     1,
    "CONCENTRATION_RISK":   2,
    "PRICING_SHIFT":        2,
    "GROWTH_SIGNAL":        2,
    "METRIC_ALERT":         3,
    "INVENTORY_SHIFT":      3,
    # Insight-layer types
    "RISK":                 2,
    "TRADEOFF":             2,
    "LEAKAGE":              3,
    "OPPORTUNITY":          4,
    # Relative layer types
    "GLOBAL_EFFECT":        3,
    "SEGMENT_RISK":         5,
    "SEGMENT_OPPORTUNITY":  5,
    "UNIFORM_PERFORMANCE":  6,
    # Filler / context
    "STRUCTURAL_CHANGE":    4,
    "SIGNAL_CONTEXT":       7,
}

_PRIORITY_RANK: dict[str, int] = {"HIGH": 0, "CRITICAL": 0, "MEDIUM": 1, "LOW": 2}


def _compress_decisions(
    *,
    global_decisions: list[dict[str, Any]],
    aegis_insights: list[dict[str, Any]],
    relative_decisions: list[dict[str, Any]],
    max_output: int = 5,
) -> list[dict[str, Any]]:
    """
    Merge all decision sources into a single ranked list of top N decisions.

    Ranking: type priority → declared priority → impact → confidence.
    Deduplicates by metric set to avoid redundant entries.
    """
    all_items: list[dict[str, Any]] = []

    # ── Normalize each source into a common shape ─────────────────────
    for d in (global_decisions or []):
        all_items.append({
            "source":     "global",
            "type":       d.get("type", "UNKNOWN"),
            "title":      d.get("title", d.get("fact", "")),
            "summary":    d.get("summary", d.get("pattern", "")),
            "action":     d.get("decision", d.get("action", "")),
            "priority":   d.get("priority", "MEDIUM"),
            "confidence": d.get("confidence", 0.0),
            "impact":     d.get("impact_score", d.get("impact", 0.0)) if isinstance(d.get("impact_score", d.get("impact", 0.0)), (int, float)) else 0.0,
            "signals":    d.get("signals", []),
            "metric":     ", ".join(d.get("signals", [])[:2]) or d.get("metric", ""),
        })

    for i in (aegis_insights or []):
        all_items.append({
            "source":     "insight",
            "type":       i.get("type", "UNKNOWN"),
            "title":      i.get("title", ""),
            "summary":    i.get("fact", i.get("pattern", "")),
            "action":     i.get("impact", ""),
            "priority":   "HIGH" if i.get("confidence", 0) >= 0.80 else "MEDIUM",
            "confidence": i.get("confidence", 0.0),
            "impact":     i.get("confidence", 0.0),  # importance proxy
            "signals":    [],
            "metric":     i.get("title", "").split(" ")[0] if i.get("title") else "",
        })

    for r in (relative_decisions or []):
        all_items.append({
            "source":     "relative",
            "type":       r.get("type", "UNKNOWN"),
            "title":      r.get("insight", ""),
            "summary":    r.get("insight", ""),
            "action":     r.get("action", ""),
            "priority":   r.get("priority", "LOW"),
            "confidence": abs(r.get("deviation", 0.0)),  # deviation as confidence proxy
            "impact":     abs(r.get("deviation", 0.0)),
            "signals":    [],
            "metric":     r.get("metric", ""),
        })

    if not all_items:
        return []

    # ── Rank ──────────────────────────────────────────────────────────
    all_items.sort(key=lambda x: (
        _TYPE_RANK.get(x["type"], 8),
        _PRIORITY_RANK.get(x["priority"], 3),
        -x["impact"],
        -x["confidence"],
    ))

    # ── Deduplicate by metric (keep first = highest ranked) ──────────
    seen_metrics: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in all_items:
        metric_key = item["metric"].lower().strip()
        if metric_key and metric_key in seen_metrics:
            continue
        if metric_key:
            seen_metrics.add(metric_key)
        deduped.append(item)

    return deduped[:max_output]


def _translate_profile_names(profile, mapping: dict[str, str]):
    """Align profiler output (raw names) with post-SemanticMapper column names."""
    def _t(name):
        return mapping.get(name, name) if name else None

    def _t_list(names):
        return sorted(set(_t(n) for n in names if _t(n) is not None))

    profile.time_column = _t(profile.time_column)
    profile.year_column = _t(profile.year_column)
    profile.month_column = _t(profile.month_column)
    profile.valid_metrics = _t_list(profile.valid_metrics)
    profile.dimensions = _t_list(profile.dimensions)
    profile.temporal_columns = _t_list(profile.temporal_columns)
    profile.ignored_columns = _t_list(profile.ignored_columns)

    for cp in profile.column_profiles:
        cp.name = mapping.get(cp.name, cp.name)

    return profile


# ─────────────────────────────────────────────
# DB Dependency
# ─────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────
# Safe CSV Reader
# ─────────────────────────────────────────────
def _read_csv_safe(content: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(BytesIO(content), encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(BytesIO(content), encoding="latin1")


# ─────────────────────────────────────────────
# Safe Timestamp Converter
# ─────────────────────────────────────────────
def _safe_to_timestamp(bucket: Any) -> float:
    if isinstance(bucket, pd.Period):
        return bucket.to_timestamp().timestamp()
    if isinstance(bucket, pd.Timestamp):
        return bucket.timestamp()
    if isinstance(bucket, (int, float)):
        return float(bucket)
    if isinstance(bucket, str):
        try:
            return pd.Timestamp(bucket).timestamp()
        except Exception:
            return 0.0
    try:
        return pd.Timestamp(bucket).timestamp()
    except Exception:
        return 0.0


# ─────────────────────────────────────────────
# Event Store Writers
# ─────────────────────────────────────────────
def _write_snapshot_events(tenant_id: str, domain: str, current_stats: dict):
    events = [
        {"domain": domain, "metric": m, "value": float(s["mean"])}
        for m, s in current_stats.get("numeric", {}).items()
        if isinstance(s, dict) and "mean" in s
    ]
    if events:
        event_store.write(tenant=tenant_id, events=events, confidence=1.0)


def _write_historical_backfill(
    tenant_id: str, domain: str, df: pd.DataFrame, timestamp_col: str,
):
    df = df.copy()
    df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce")
    df = df.dropna(subset=[timestamp_col])
    df["__bucket"] = df[timestamp_col].dt.to_period("M")

    for bucket, group in df.groupby("__bucket"):
        bucket_ts = _safe_to_timestamp(bucket)
        means = group.select_dtypes(include="number").mean()
        events = [
            {"domain": domain, "metric": m, "value": float(v)}
            for m, v in means.items() if not pd.isna(v)
        ]
        if events:
            event_store.write(tenant=tenant_id, events=events,
                              confidence=1.0, ts_override=bucket_ts)


def _write_composite_backfill(
    tenant_id: str, domain: str, df: pd.DataFrame,
    year_col: str, month_col: str | None,
):
    df = df.copy()
    try:
        if month_col:
            df["__ts"] = pd.to_datetime(
                df[year_col].astype(str) + "-" +
                df[month_col].astype(str).str.zfill(2) + "-01",
                errors="coerce",
            )
        else:
            df["__ts"] = pd.to_datetime(
                df[year_col].astype(str) + "-07-01", errors="coerce"
            )
    except Exception as e:
        log.warning(f"[COMPOSITE_BACKFILL] Timestamp construction failed: {e}")
        return

    df = df.dropna(subset=["__ts"])
    df["__bucket"] = df["__ts"].dt.to_period("M")
    exclude = {"__ts", "__bucket", year_col} | ({month_col} if month_col else set())

    for bucket, group in df.groupby("__bucket"):
        bucket_ts = _safe_to_timestamp(bucket)
        metric_cols = [c for c in group.select_dtypes(include="number").columns
                       if c not in exclude]
        if not metric_cols:
            continue
        means = group[metric_cols].mean()
        events = [
            {"domain": domain, "metric": m, "value": float(v)}
            for m, v in means.items() if not pd.isna(v)
        ]
        if events:
            event_store.write(tenant=tenant_id, events=events,
                              confidence=1.0, ts_override=bucket_ts)


# ─────────────────────────────────────────────
# MAIN ANALYZE ROUTE
# ─────────────────────────────────────────────
def _load_previous_numeric_baseline(db, tenant_id: str, domain: str, metrics: list[str]) -> dict[str, dict[str, float]]:
    baseline_stats: dict[str, dict[str, float]] = {}

    for metric in metrics:
        try:
            base = get_last_baseline(
                session=db,
                tenant=tenant_id,
                domain=domain,
                category="numeric",
                column=metric,
            )
            if base is None or base.mean is None or base.std is None:
                continue
            baseline_stats[metric] = {
                "mean": float(base.mean),
                "median": float(base.median) if base.median is not None else None,
                "std": float(base.std),
                "min": float(base.min) if base.min is not None else None,
                "max": float(base.max) if base.max is not None else None,
                "null_ratio": float(base.null_ratio) if base.null_ratio is not None else 0.0,
                "zero_ratio": float(base.zero_ratio) if base.zero_ratio is not None else 0.0,
            }
        except Exception as e:
            log.warning(f"[BASELINE_LOAD] previous baseline unavailable for {metric}: {e}")
            continue

    return baseline_stats


@router.post("/api/analyze/{domain}")
def analyze_data(
    domain: str,
    request: Request,
    file: UploadFile = File(...),
    x_api_key: str = Header(None, alias="X-API-Key"),
    db=Depends(get_db),
):
    # ── AUTH ──────────────────────────────────
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API Key")

    tenant_id = request.scope.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant not resolved")

    # ── LOAD CSV ──────────────────────────────
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    # Size guard — reject >500MB uploads to prevent OOM on long-running workers.
    _MAX_UPLOAD_BYTES = 500 * 1024 * 1024
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content)} bytes; max {_MAX_UPLOAD_BYTES})",
        )

    try:
        df_raw = _read_csv_safe(content)
    except Exception as e:
        log.error(f"[CSV_PARSE_FAIL] tenant={tenant_id} err={e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {type(e).__name__}")

    # ── Input validation (production hardening) ────────────────────────
    if df_raw is None or df_raw.empty:
        raise HTTPException(status_code=400, detail="CSV contains no data")
    if len(df_raw.columns) < 2:
        raise HTTPException(
            status_code=400,
            detail="CSV must have at least 2 columns",
        )
    if len(df_raw) < 10:
        raise HTTPException(
            status_code=400,
            detail=f"Too few rows ({len(df_raw)}) — minimum 10 required",
        )
    # Reject pathological duplicate column names (pandas silently disambiguates).
    if len(set(df_raw.columns)) != len(df_raw.columns):
        raise HTTPException(
            status_code=400,
            detail="Duplicate column names detected",
        )

    log.info(
        f"[ANALYZE] tenant={tenant_id} domain={domain} "
        f"rows={len(df_raw)} cols={len(df_raw.columns)} bytes={len(content)}"
    )

    # ── 1. DATASET PROFILER (runs on raw df) ──
    # Must be first — tells every downstream component what is safe to analyse
    profile = _profiler.profile(df_raw)

    for w in profile.warnings:
        log.warning(f"[PROFILER] {w}")

    # ── 2. SANITIZE ───────────────────────────
    sanitizer = DataSanitizer()
    df = sanitizer.sanitize(df_raw)

    # ── 3. SEMANTIC MAP + COLLISION GUARD ─────
    mapper = SemanticMapper(session=db)
    df, raw_mappings = mapper.map_columns(df, tenant_id, domain, preserve_columns=profile.dimensions)

    safe_mappings = deduplicate_semantic_mappings(raw_mappings)

    if safe_mappings != raw_mappings:
        collisions = {
            orig: {"was": raw_mappings[orig], "resolved_to": safe_mappings[orig]}
            for orig in raw_mappings
            if raw_mappings[orig] != safe_mappings[orig]
        }
        log.warning(f"[ANALYZE] Semantic collisions resolved: {collisions}")
        rename_corrections = {
            raw_mappings[orig]: safe_mappings[orig]
            for orig in raw_mappings
            if raw_mappings[orig] != safe_mappings[orig]
               and raw_mappings[orig] in df.columns
        }
        if rename_corrections:
            df = df.rename(columns=rename_corrections)

    # ── 3b. ALIGN PROFILER NAMES TO MAPPED DF ─
    profile = _translate_profile_names(profile, safe_mappings)

    # ── 4. REALITY PROFILE ────────────────────
    reader = RealityReader()
    reality = reader.profile(df)
    current_stats = {"numeric": reality.get("stats", {})}
    previous_numeric_baseline = _load_previous_numeric_baseline(
        db=db,
        tenant_id=tenant_id,
        domain=domain,
        metrics=list(current_stats["numeric"].keys()),
    )

    # ── 5. QUALITY ────────────────────────────
    quality_gate = QualityGate()
    quality_report = quality_gate.assess(current_stats["numeric"])

    # ── 6. DRIFT ──────────────────────────────
    detector = DriftDetector()
    drift_report = detector.detect_and_store(
        session=db, tenant=tenant_id, domain=domain, current_stats=current_stats,
    )

    # ── 7. BASELINE SNAPSHOT ──────────────────
    persist_reality_snapshot(
        session=db, tenant=tenant_id, domain=domain,
        reality={"stats": current_stats},
    )

    # ── 8. TEMPORAL MODE DETECTION ────────────
    # Use profiler output — it already found the time column
    data_mode    = "snapshot"
    ordered_data = profile.ordered_data
    time_column  = profile.time_column

    if profile.time_column and profile.time_column in df.columns:
        try:
            span = (
                pd.to_datetime(df[profile.time_column], errors="coerce").max()
                - pd.to_datetime(df[profile.time_column], errors="coerce").min()
            ).days
            if span > 30:
                _write_historical_backfill(tenant_id, domain, df, profile.time_column)
                data_mode = "backfill"
            else:
                _write_snapshot_events(tenant_id, domain, current_stats)
        except Exception as e:
            log.warning(f"[TIMESTAMP_FAIL] {e}")
            _write_snapshot_events(tenant_id, domain, current_stats)

    elif profile.year_column:
        try:
            _write_composite_backfill(
                tenant_id, domain, df,
                profile.year_column, profile.month_column,
            )
            data_mode = "composite_backfill"
            time_column = profile.year_column
        except Exception as e:
            log.warning(f"[COMPOSITE_BACKFILL_FAIL] {e}")
            _write_snapshot_events(tenant_id, domain, current_stats)

    else:
        _write_snapshot_events(tenant_id, domain, current_stats)

    # ── 9. COMPANY BRAIN V2 ───────────────────
    _brain_cols = sorted(set(
        profile.valid_metrics
        + profile.dimensions
        + [c for c in (profile.time_column, profile.year_column, profile.month_column) if c]
    ))
    _brain_cols = [c for c in _brain_cols if c in df.columns]
    brain_df = df[_brain_cols] if _brain_cols else df

    brain_output = run_company_brain_v2(
        df=brain_df,
        historical_row_count=len(df),
        baseline_numeric_stats=current_stats["numeric"],
        bias_baseline_stats=previous_numeric_baseline,
        domain=domain,
    )

    # ── 9b. F-05: BASELINE MATURITY GATING ─────
    # Penalise confidence when baseline is immature (few uploads).
    try:
        upload_count = get_upload_count(db, tenant_id, domain)
        if upload_count < 2:
            maturity = "IMMATURE"
            maturity_multiplier = 0.80
        elif upload_count < 5:
            maturity = "DEVELOPING"
            maturity_multiplier = 0.90
        else:
            maturity = "MATURE"
            maturity_multiplier = 1.0

        if maturity_multiplier < 1.0:
            for insight in brain_output.get("insights", []):
                original = insight.get("confidence", 0.0)
                insight["confidence"] = round(original * maturity_multiplier, 3)
            brain_output.setdefault("metadata", {})["baseline_maturity"] = maturity
            brain_output.setdefault("metadata", {})["upload_count"] = upload_count
    except Exception as e:
        log.warning(f"[BASELINE_MATURITY] {e}")

    # ── 10. FORECASTS ─────────────────────────
    brain_output = attach_forecasts_to_brain_output(
        brain_output=brain_output,
        event_store_db=event_store.db,
        tenant=tenant_id,
        domain=domain,
        baseline_numeric_stats=current_stats["numeric"],
    )

    # ── 10b. ENRICH SIGNALS WITH SEGMENT CONTEXT ─
    try:
        brain_output["insights"] = enrich_signals_with_segments(
            insights=brain_output["insights"],
            df=df,
            dimensions=profile.dimensions,
            valid_metrics=profile.valid_metrics,
        )
    except Exception as e:
        log.warning(f"[SEGMENT_ENRICHMENT] {e}")

    # ── 10c. DESCRIPTIVE INTELLIGENCE LAYER ───
    descriptive_insights: list = []
    try:
        descriptive_insights = compute_descriptive_insights(
            df=df,
            valid_metrics=profile.valid_metrics,
            dimensions=profile.dimensions,
        )
    except Exception as e:
        log.warning(f"[DESCRIPTIVE_PROFILER] {e}")

    # ── 11. SNAPSHOT SAVE ─────────────────────
    CognitiveSnapshotService.persist(
        db=db, tenant=tenant_id,
        brain_name="company_brain_v2",
        model_version="2.1.0",
        system_state=brain_output["system_state"],
        insights=brain_output["insights"],
        snapshot_blob=brain_output,
    )

    # ── 12. GLOBAL DECISION PIPELINE ──────────
    # F-07: Enforce TRUE SILENCE — if the brain says SILENT or OBSERVATION,
    # the decision pipeline must not produce decisions. This prevents the
    # contradictory state of system_state="SILENT" + 3 decisions.
    if brain_output["system_state"] not in (
        SystemState.INSIGHTFUL.value, "INSIGHTFUL",
    ):
        decisions_output = {
            "decisions": [],
            "decision_meta": {
                "skipped": True,
                "reason": f"system_state={brain_output['system_state']} — silence enforced",
            },
        }
    else:
        try:
            decisions_output = run_decision_pipeline(
                company_insights=brain_output["insights"],
                tenant_id=tenant_id,
                ordered_data=ordered_data,
                reality_snapshot=current_stats,
                df=df,
                time_column=time_column,
                baseline_stats=current_stats["numeric"],
                valid_metrics=profile.valid_metrics,
                metric_roles=brain_output.get("metric_roles"),
            )
        except Exception as e:
            log.error(f"[DECISION_PIPELINE_ERROR] {e}", exc_info=True)
            decisions_output = {"decisions": [], "decision_meta": {"error": str(e)}}

    global_decisions = decisions_output.get("decisions", [])

    # ── Replace signals with validated versions ──────────────────────
    # correctness_layer has resolved direction, rejected noise, and
    # corrected inversions. All downstream consumers must use these.
    validated_events = decisions_output.get("validated_events")
    if validated_events is not None:
        brain_output["insights"] = validated_events
        # ── Regenerate narrative from validated signals ───────────────
        # The narrative was generated before correctness ran (step 10).
        # Rebuild it now so it matches the validated directions exactly.
        try:
            # Adapt validated events to the narrative's expected structure:
            # _generate_narrative reads insight["subtype"] for BIAS direction.
            # Validated events store direction in ["direction"] (normalised).
            # Map each event to a narrative-compatible shape.
            narrative_signals = []
            for ev in validated_events:
                adapted = dict(ev)
                # subtype drives the narrative verb ("upward" / "downward")
                adapted["subtype"] = ev.get("direction", ev.get("subtype", ""))
                narrative_signals.append(adapted)
            brain_output["narrative"] = generate_narrative(
                system_state=SystemState(brain_output["system_state"]),
                insights=narrative_signals,
                domain=domain,
                row_count=profile.row_count,
            )
        except Exception as _ne:
            log.warning(f"[NARRATIVE_REGEN] {_ne}")

    # ── 12b. CROSS-VALIDATE DECISIONS ───────────
    try:
        global_decisions = cross_validate_decisions(
            decisions=global_decisions,
            signals=brain_output["insights"],
            domain=domain,
        )
    except Exception as e:
        log.warning(f"[CROSS_VALIDATOR] {e}")

    # ── 12c. ECONOMIC INTERPRETATION ───────────
    # Phase 2: Attach economic semantics to every decision
    try:
        global_decisions = enrich_with_economics(
            global_decisions,
            metadata=brain_output.get("metadata"),
        )
    except Exception as e:
        log.warning(f"[ECONOMIC_INTERPRETER] {e}")

    # ── 13. SEGMENT ENGINE ────────────────────
    segment_decisions: dict = {}
    try:
        # Use validated signals — segments explain metrics, not generate signals
        segment_decisions = generate_segment_decisions(
            df=df,
            dimensions=profile.dimensions,
            baseline_stats=current_stats["numeric"],
            global_decisions=global_decisions,
            ordered_data=ordered_data,
            valid_metrics=profile.valid_metrics,
            validated_signals=brain_output["insights"],
        )
    except Exception as e:
        log.error(f"[SEGMENT_ENGINE_ERROR] {e}", exc_info=True)

    # ── 14. EXPLAINABILITY (DECISION CARDS) ───
    try:
        explainer = DecisionExplainer()
        decision_cards = explainer.explain(global_decisions)
    except Exception as e:
        log.error(f"[DECISION_EXPLAINER_ERROR] {e}", exc_info=True)
        decision_cards = []

    # ── 13b. INSIGHT LAYER ────────────────────
    # Converts signals + segments + descriptive intelligence
    # into 3–5 prioritized typed insights (RISK/OPPORTUNITY/LEAKAGE/TRADEOFF)
    aegis_insights: list = []
    try:
        aegis_insights = generate_insights(
            validated_signals=brain_output["insights"],
            segment_decisions=segment_decisions,
            descriptive_insights=descriptive_insights,
            total_rows=profile.row_count,
        )
    except Exception as e:
        log.warning(f"[INSIGHT_LAYER] {e}")

    # ── 14b. RELATIVE INTELLIGENCE ──────────────
    # Segment-vs-global comparison layer. Independent of system_state —
    # produces relative insights even when global decisions are empty.
    # Runs on df + dimensions, does not touch signals/decisions.
    relative_decisions: list = []
    try:
        relative_decisions = compute_relative_decisions(
            df=df,
            valid_metrics=profile.valid_metrics,
            dimensions=profile.dimensions,
            system_state=brain_output.get("system_state", ""),
            numeric_stats=current_stats.get("numeric"),
        )
    except Exception as e:
        log.warning(f"[RELATIVE_INTELLIGENCE] {e}")

    # ── 15. OUTPUT CLEANUP ────────────────────
    # Strip low-value descriptive insights from client output.
    # LOW/INFO severity items (BOTTOM_PERFORMERS, weak anomalies) are noise.
    # The insight_layer already consumed the full list for RISK/LEAKAGE detection.
    descriptive_insights = [
        di for di in descriptive_insights
        if di.get("severity") in ("HIGH", "MEDIUM")
    ]

    # Filter drift_report to valid metrics only — strip identifiers & dimensions
    valid_metric_set = set(profile.valid_metrics)
    if isinstance(drift_report, dict) and "numeric" in drift_report:
        drift_report["numeric"] = {
            k: v for k, v in drift_report["numeric"].items()
            if k in valid_metric_set
        }
        # Align drift status with validated signals
        for sig in brain_output.get("insights", []):
            m = sig.get("metric", "")
            vdir = sig.get("validated_direction", sig.get("direction", ""))
            if m in drift_report["numeric"] and vdir in ("UPWARD", "DOWNWARD"):
                entry = drift_report["numeric"][m]
                if entry.get("status") == "STABLE":
                    b_mean = entry.get("baseline_mean")
                    c_mean = entry.get("current_mean")
                    if b_mean is not None and c_mean is not None and abs(b_mean) > 1e-9:
                        if abs(c_mean - b_mean) / abs(b_mean) > 0.05:
                            entry["status"] = "DRIFT_DETECTED"
                            entry["validated_direction"] = vdir
                            entry["drift_type"] = "validated_signal_override"

    log.info(
        f"[ANALYZE] Complete — tenant={tenant_id} domain={domain} "
        f"state={brain_output['system_state']} "
        f"insights={len(brain_output['insights'])} "
        f"global_decisions={len(global_decisions)} "
        f"segments={len(segment_decisions)} "
        f"descriptive={len(descriptive_insights)} "
        f"data_mode={data_mode} ordered={ordered_data} "
        f"quality={profile.data_quality_score}"
    )

    # ── 16. DECISION COMPRESSION ─────────────
    # Merge all decision sources into a ranked top-5 list.
    # Original lists are preserved for debugging; final_decisions is the
    # client-facing, compressed output.
    final_decisions = _compress_decisions(
        global_decisions=global_decisions,
        aegis_insights=aegis_insights,
        relative_decisions=relative_decisions,
    )

    # ── 17. STRUCTURED OUTPUT + NARRATION ─────
    # Pure transformation layer — maps all pipeline outputs into canonical schema.
    # Narration depends ONLY on this structured JSON.
    _profile_block = {
        "time_column":         profile.time_column,
        "year_column":         profile.year_column,
        "month_column":        profile.month_column,
        "valid_metrics":       profile.valid_metrics,
        "dimensions":          profile.dimensions,
        "ignored_columns":     profile.ignored_columns,
        "data_quality_score":  profile.data_quality_score,
        "ordered_data":        profile.ordered_data,
        "row_count":           profile.row_count,
        "warnings":            profile.warnings,
    }

    try:
        structured_analysis = compose_structured_output(
            system_state=brain_output["system_state"],
            profile=_profile_block,
            quality_report=quality_report,
            final_decisions=final_decisions,
            global_decisions=global_decisions,
            company_insights=brain_output.get("insights", []),
            aegis_insights=aegis_insights,
            relative_decisions=relative_decisions,
            segment_decisions=segment_decisions,
            descriptive_insights=descriptive_insights,
            decision_meta=decisions_output.get("decision_meta", {}),
            reality_snapshot=current_stats,
            drift_report=drift_report,
            metadata=brain_output.get("metadata", {}),
            tenant_id=tenant_id,
            domain=domain,
            data_mode=data_mode,
        )
    except Exception as e:
        log.error(f"[STRUCTURED_OUTPUT] {e}", exc_info=True)
        structured_analysis = {"state": "NO_SIGNAL", "error": str(e)}

    try:
        narration_text = generate_narration(structured_analysis)
    except Exception as e:
        log.error(f"[NARRATION] {e}", exc_info=True)
        narration_text = ""

    narration_meta = build_narration_meta(
        structured_analysis, narration_text, mode="template",
    )

    # ── RESPONSE ──────────────────────────────

    if not global_decisions:
        return _sanitize_for_json({
            "status": "NO_SIGNIFICANT_CHANGE",
            "message": "No meaningful structural changes detected in the dataset",

            "tenant": tenant_id,
            "domain": domain,
            "data_mode": data_mode,
            "profile": _profile_block,

            "system_state": brain_output["system_state"],
            "narrative": "",
            "company_insights": [],

            "final_decisions":    final_decisions,
            "global_decisions": [],
            "segment_decisions": segment_decisions,
            "decision_cards": [],
            "decision_meta": decisions_output.get("decision_meta", {}),
            "aegis_insights": aegis_insights,
            "descriptive_insights": descriptive_insights,
            "relative_decisions": relative_decisions,

            "forecasts": brain_output.get("forecasts", {}),
            "drift_report": drift_report,
            "quality_report": quality_report,
            "reality_snapshot": current_stats,
            "semantic_mappings": safe_mappings,
            "metadata": brain_output.get("metadata", {}),

            # Universal structured output + narration (additive)
            "analysis": structured_analysis,
            "narration": narration_text,
            "narration_meta": narration_meta,
        })

    return _sanitize_for_json({
        "status":       "LIVE",
        "tenant":       tenant_id,
        "domain":       domain,
        "data_mode":    data_mode,
        "profile":      _profile_block,

        "system_state":   brain_output["system_state"],
        "narrative":      brain_output.get("narrative", ""),
        "company_insights": brain_output["insights"],

        # Client-facing compressed decisions
        "final_decisions":   final_decisions,

        # Full detail — preserved for debugging / advanced consumers
        "global_decisions":  global_decisions,
        "segment_decisions": segment_decisions,
        "decision_cards":    decision_cards,
        "decision_meta":     decisions_output.get("decision_meta", {}),
        "aegis_insights":     aegis_insights,
        "descriptive_insights": descriptive_insights,
        "relative_decisions": relative_decisions,

        "forecasts":         brain_output.get("forecasts", {}),
        "drift_report":      drift_report,
        "quality_report":    quality_report,
        "reality_snapshot":  current_stats,
        "semantic_mappings": safe_mappings,
        "metadata":          brain_output.get("metadata", {}),

        # Universal structured output + narration (additive)
        "analysis":          structured_analysis,
        "narration":         narration_text,
        "narration_meta":    narration_meta,
    })


# ─────────────────────────────────────────────────────────────────────────────
# CHAT ENDPOINT — grounded Q&A from structured output
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/chat")
async def chat(request: Request):
    """
    Answer a natural language question using ONLY the AEGIS structured output.
    The LLM never sees raw data — only the canonical JSON schema.

    Request body:
        { "question": "...", "analysis": { ... structured output ... } }

    Response:
        { "answer": "...", "grounded": true, "source": "gemma|keyword_fallback", "mode": "llm|template" }
    """
    body = await request.json()
    question = body.get("question", "")
    analysis = body.get("analysis", {})

    if not question:
        return {"answer": "Please provide a question.", "grounded": True, "source": "validation", "mode": "none"}

    if not analysis:
        return {"answer": "No analysis data provided.", "grounded": True, "source": "validation", "mode": "none"}

    result = answer_question(question, analysis)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# LLM HEALTH ENDPOINT — Gemma/Ollama status
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health/llm")
async def llm_health():
    """
    Cheap health check (no inference) — safe for the FE 5s timeout.

    Response:
        { available, latency_ms, model, model_installed, model_loaded,
          installed_models, error }
    """
    from aegis_ai.llm.call_gemma import check_gemma_health
    return check_gemma_health()


@router.post("/health/llm/warmup")
async def llm_warmup():
    """
    Force-load the configured model into memory. Slow on first call (60-120s
    on this hardware); near-instant once warm. Subsequent /chat and narration
    requests then hit the model at full eval speed.
    """
    from aegis_ai.llm.call_gemma import warmup_gemma
    return warmup_gemma()

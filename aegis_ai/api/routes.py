# aegis_ai/api/routes.py

import logging
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from pandas import Period

from ..db.session import SessionLocal
from ..sanitizer.data_sanitizer import DataSanitizer
from ..sanitizer.semantic_mapper import SemanticMapper, TIMESTAMP_FIELDS
from ..sanitizer.quality_gate import QualityGate
from ..brains.reality_reader import RealityReader
from ..brains.drift_detector import DriftDetector
from ..db.baselines.persistence import persist_reality_snapshot
from ..spine.event_store import EventStore

# V2 Intelligence
from ..company_brain.orchestrator_v2 import run_company_brain_v2
from ..services.cognitive_snapshot_service import CognitiveSnapshotService

# Forecast layer
from ..company_brain.forecast_integration import attach_forecasts_to_brain_output


router = APIRouter()
log = logging.getLogger("aegis_ai.api.routes")

event_store = EventStore()


# ──────────────────────────────────────────────────────
# DB Dependency
# ──────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ──────────────────────────────────────────────────────
# Safe CSV Reader (utf-8 with latin1 fallback)
# ──────────────────────────────────────────────────────
def _read_csv_safe(content: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(BytesIO(content), encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(BytesIO(content), encoding="latin1")


# ──────────────────────────────────────────────────────
# Snapshot Event Writer — TENANT SAFE
# ──────────────────────────────────────────────────────
def _write_snapshot_events(tenant_id: str, domain: str, current_stats: dict):

    if not tenant_id:
        raise ValueError("tenant_id required for event write")

    numeric_stats = current_stats.get("numeric", {})

    events = [
        {
            "domain": domain,
            "metric": metric,
            "value": float(stats["mean"]),
        }
        for metric, stats in numeric_stats.items()
        if isinstance(stats, dict) and "mean" in stats
    ]

    if events:
        event_store.write(
            tenant=tenant_id,
            events=events,
            confidence=1.0,
        )


# ──────────────────────────────────────────────────────
# Historical Backfill Writer — TENANT SAFE
# ──────────────────────────────────────────────────────
def _write_historical_backfill(
    tenant_id: str,
    domain: str,
    df: pd.DataFrame,
    timestamp_col: str,
):

    if not tenant_id:
        raise ValueError("tenant_id required for event write")

    df = df.copy()
    df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce")
    df = df.dropna(subset=[timestamp_col])

    df["__bucket"] = df[timestamp_col].dt.to_period("M")
    grouped = df.groupby("__bucket")

    for bucket, group in grouped:

        bucket_ts = bucket.to_timestamp().timestamp()  # type: ignore[attr-defined]
        numeric_means = group.select_dtypes(include="number").mean()

        events = [
            {
                "domain": domain,
                "metric": metric,
                "value": float(value),
            }
            for metric, value in numeric_means.items()
            if not pd.isna(value)
        ]

        if events:
            event_store.write(
                tenant=tenant_id,
                events=events,
                confidence=1.0,
                ts_override=bucket_ts,
            )


# ──────────────────────────────────────────────────────
# MAIN ANALYZE ROUTE
# ──────────────────────────────────────────────────────
@router.post("/api/analyze/{domain}")
def analyze_data(
    domain: str,
    request: Request,
    file: UploadFile = File(...),
    x_api_key: str = Header(None, alias="X-API-Key"),
    db=Depends(get_db),
):
    # ── AUTH ──────────────────────────────────────────
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API Key")

    tenant_id = request.scope.get("tenant_id")

    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant not resolved")

    # ── LOAD CSV ──────────────────────────────────────
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    df = _read_csv_safe(content)

    if df.empty:
        raise HTTPException(status_code=400, detail="CSV contains no data")

    log.info(f"[ANALYZE] tenant={tenant_id} domain={domain} rows={len(df)} cols={len(df.columns)}")

    # ── SANITIZE ──────────────────────────────────────
    sanitizer = DataSanitizer()
    df = sanitizer.sanitize(df)

    # ── SEMANTIC MAP ──────────────────────────────────
    mapper = SemanticMapper(session=db)
    df, mappings = mapper.map_columns(df, tenant_id, domain)

    # ── REALITY PROFILE ───────────────────────────────
    reader = RealityReader()
    reality = reader.profile(df)
    current_stats = {"numeric": reality.get("stats", {})}

    # ── QUALITY ───────────────────────────────────────
    quality_gate = QualityGate()
    quality_report = quality_gate.assess(current_stats["numeric"])

    # ── DRIFT ─────────────────────────────────────────
    detector = DriftDetector()
    drift_report = detector.detect_and_store(
        session=db,
        tenant=tenant_id,
        domain=domain,
        current_stats=current_stats,
    )

    # ── BASELINE SNAPSHOT ─────────────────────────────
    persist_reality_snapshot(
        session=db,
        tenant=tenant_id,
        domain=domain,
        reality={"stats": current_stats},
    )

    # ── EVENT STORE WRITES ────────────────────────────
    timestamp_col = next((c for c in df.columns if c in TIMESTAMP_FIELDS), None)

    if timestamp_col:
        try:
            time_span_days = (
                df[timestamp_col].max() - df[timestamp_col].min()
            ).days

            if time_span_days > 30:
                log.info(f"[ANALYZE] Historical backfill activated — {time_span_days} days")
                _write_historical_backfill(tenant_id, domain, df, timestamp_col)
            else:
                log.info("[ANALYZE] Snapshot mode")
                _write_snapshot_events(tenant_id, domain, current_stats)
        except Exception as e:
            log.warning(f"[ANALYZE] Timestamp processing failed, using snapshot mode: {e}")
            _write_snapshot_events(tenant_id, domain, current_stats)
    else:
        log.info("[ANALYZE] No semantic timestamp found — snapshot mode")
        _write_snapshot_events(tenant_id, domain, current_stats)

    # ── COMPANY BRAIN V2 ──────────────────────────────
    brain_output = run_company_brain_v2(
        df=df,
        historical_row_count=len(df),
        baseline_numeric_stats=current_stats["numeric"],
        domain=domain,
    )

    # ── FORECAST LAYER ────────────────────────────────
    brain_output = attach_forecasts_to_brain_output(
        brain_output=brain_output,
        event_store_db=event_store.db,
        tenant=tenant_id,
        domain=domain,
        baseline_numeric_stats=current_stats["numeric"],
    )

    # ── SNAPSHOT PERSISTENCE ──────────────────────────
    CognitiveSnapshotService.persist(
        db=db,
        tenant=tenant_id,
        brain_name="company_brain_v2",
        model_version="2.1.0",
        system_state=brain_output["system_state"],
        insights=brain_output["insights"],
        snapshot_blob=brain_output,
    )

    log.info(
        f"[ANALYZE] Complete — tenant={tenant_id} domain={domain} "
        f"state={brain_output['system_state']} "
        f"insights={len(brain_output['insights'])}"
    )

    # ── RESPONSE ──────────────────────────────────────
    return {
        "status": "LIVE",
        "tenant": tenant_id,
        "domain": domain,
        "system_state": brain_output["system_state"],
        "narrative": brain_output.get("narrative", ""),
        "company_insights": brain_output["insights"],
        "forecasts": brain_output.get("forecasts", {}),
        "drift_report": drift_report,
        "quality_report": quality_report,
        "reality_snapshot": current_stats,
        "semantic_mappings": mappings,
        "metadata": brain_output.get("metadata", {}),
    }
import logging
from io import BytesIO
import pandas as pd
from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile

from aegis_ai.db.session import SessionLocal
from aegis_ai.sanitizer.data_sanitizer import DataSanitizer
from aegis_ai.sanitizer.semantic_mapper import SemanticMapper, TIMESTAMP_FIELDS
from aegis_ai.sanitizer.quality_gate import QualityGate
from aegis_ai.brains.reality_reader import RealityReader
from aegis_ai.brains.drift_detector import DriftDetector
from aegis_ai.db.baselines.persistence import persist_reality_snapshot
from aegis_ai.spine.event_store import EventStore

# ✅ V2 Intelligence
from aegis_ai.company_brain.orchestrator_v2 import run_company_brain_v2
from aegis_ai.services.cognitive_snapshot_service import CognitiveSnapshotService


router = APIRouter()
log = logging.getLogger("aegis_ai.api.routes")

event_store = EventStore()


# ------------------------------------------------------------
# DB Dependency
# ------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ------------------------------------------------------------
# Demo API Keys
# ------------------------------------------------------------
VALID_API_KEYS = {
    "tenant_alpha",
    "f4ccaadbeab547f61f3d31e8f18bc6e8a54f763e6641b865",
}


# ------------------------------------------------------------
# Safe CSV Reader
# ------------------------------------------------------------
def _read_csv_safe(content: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(BytesIO(content), encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(BytesIO(content), encoding="latin1")


# ------------------------------------------------------------
# Snapshot Event Writer
# ------------------------------------------------------------
def _write_snapshot_events(domain: str, current_stats: dict):

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
        event_store.write(events, confidence=1.0)


# ------------------------------------------------------------
# Historical Backfill Writer
# ------------------------------------------------------------
def _write_historical_backfill(domain: str, df: pd.DataFrame, timestamp_col: str):

    df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce")
    df = df.dropna(subset=[timestamp_col])

    df["__bucket"] = df[timestamp_col].dt.to_period("M")
    grouped = df.groupby("__bucket")

    for bucket, group in grouped:

        bucket_ts = bucket.start_time.timestamp()
        numeric_means = group.select_dtypes(include="number").mean()

        events = [
            {
                "domain": domain,
                "metric": metric,
                "value": float(value),
            }
            for metric, value in numeric_means.items()
        ]

        if events:
            event_store.write(
                events,
                confidence=1.0,
                ts_override=bucket_ts,
            )


# ------------------------------------------------------------
# MAIN ANALYZE ROUTE
# ------------------------------------------------------------
@router.post("/api/analyze/{domain}")
def analyze_data(
    domain: str,
    request: Request,
    file: UploadFile = File(...),
    x_api_key: str = Header(None, alias="X-API-Key"),
    db=Depends(get_db),
):

    # ---------------- AUTH ----------------
    if not x_api_key or x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    tenant_id = request.scope.get("tenant_id", "tenant_alpha")

    # ---------------- LOAD CSV ----------------
    content = file.file.read()
    df = _read_csv_safe(content)

    # ---------------- SANITIZE ----------------
    sanitizer = DataSanitizer()
    df = sanitizer.sanitize(df)

    # ---------------- SEMANTIC MAP ----------------
    mapper = SemanticMapper(session=db)
    df, mappings = mapper.map_columns(df, tenant_id, domain)

    # ---------------- REALITY PROFILE ----------------
    reader = RealityReader()
    reality = reader.profile(df)
    current_stats = {"numeric": reality.get("stats", {})}

    # ---------------- QUALITY ----------------
    quality_gate = QualityGate()
    quality_report = quality_gate.assess(current_stats["numeric"])

    # ---------------- DRIFT ----------------
    detector = DriftDetector()
    drift_report = detector.detect_and_store(
        session=db,
        tenant=tenant_id,
        domain=domain,
        current_stats=current_stats,
    )

    # ---------------- BASELINE SNAPSHOT ----------------
    persist_reality_snapshot(
        session=db,
        tenant=tenant_id,
        domain=domain,
        reality={"stats": current_stats},
    )

    # ---------------- EVENT STORE WRITES ----------------
    timestamp_col = next((c for c in df.columns if c in TIMESTAMP_FIELDS), None)

    if timestamp_col:
        time_span_days = (
            df[timestamp_col].max() - df[timestamp_col].min()
        ).days

        if time_span_days > 30:
            log.info("Historical backfill activated")
            _write_historical_backfill(domain, df, timestamp_col)
        else:
            log.info("Snapshot mode")
            _write_snapshot_events(domain, current_stats)
    else:
        log.info("No semantic timestamp found — snapshot mode")
        _write_snapshot_events(domain, current_stats)

    # ============================================================
    # 🧠 COMPANY BRAIN V2 (CANONICAL INTELLIGENCE)
    # ============================================================
    brain_output = run_company_brain_v2(
        df=df,
        historical_row_count=len(df),
        baseline_numeric_stats=current_stats["numeric"],
    )

    # ============================================================
    # 🧠 COGNITIVE SNAPSHOT PERSISTENCE (OUTSIDE BRAIN)
    # ============================================================
    CognitiveSnapshotService.persist(
        db=db,
        tenant=tenant_id,
        brain_name="company_brain_v2",
        model_version="2.1.0",
        system_state=brain_output["system_state"],
        insights=brain_output["insights"],
        snapshot_blob=brain_output,
    )

    # ---------------- RESPONSE ----------------
    return {
        "status": "LIVE",
        "tenant": tenant_id,
        "domain": domain,
        "semantic_mappings": mappings,
        "quality_report": quality_report,
        "reality_snapshot": current_stats,
        "drift_report": drift_report,
        "system_state": brain_output["system_state"],
        "company_insights": brain_output["insights"],
        "metadata": brain_output.get("metadata", {}),
    }
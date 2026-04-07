# aegis_ai/api/main.py

import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from starlette.middleware import Middleware

from aegis_ai.api.routes import router
from aegis_ai.core.decision_kernel import DecisionKernel
from aegis_ai.spine.event_store import EventStore
from aegis_ai.spine.lineage_audit import LineageAudit
from aegis_ai.runtime.temporal_monitor import TemporalMonitor

from aegis_ai.agents.canonical.regime_segmenter import RegimeSegmenter
from aegis_ai.agents.canonical.regime_snapshot_recorder import RegimeSnapshotRecorder
from aegis_ai.agents.canonical.segmented_tradeoff_detector import SegmentedTradeoffDetector
from aegis_ai.agents.canonical.segmented_confidence_gate import SegmentedConfidenceGate

from aegis_ai.security.tenant_middleware import TenantMiddleware
from aegis_ai.security.rate_limit_middleware import RateLimitMiddleware
from aegis_ai.db.session import Base, engine


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
log = logging.getLogger("aegis_ai.api.main")


# ─────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────
middleware = [
    Middleware(TenantMiddleware),
    Middleware(RateLimitMiddleware),
]


# ─────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────
app = FastAPI(
    title="AEGIS Enterprise Nervous System",
    version="2.0-production",
    debug=False,
    middleware=middleware,
)


# ─────────────────────────────────────────────
# Kernel Initialization (Stateless)
# ─────────────────────────────────────────────
kernel = DecisionKernel()

kernel.register(RegimeSegmenter())
kernel.register(RegimeSnapshotRecorder())
kernel.register(SegmentedTradeoffDetector())
kernel.register(SegmentedConfidenceGate())


# Infrastructure Components
gateway = kernel.gateway
store = EventStore()
audit = LineageAudit()


# ─────────────────────────────────────────────
# Global Exception Debugger (Safe)
# ─────────────────────────────────────────────
@app.exception_handler(Exception)
async def crash_debugger(request: Request, exc: Exception):
    import traceback
    return PlainTextResponse(traceback.format_exc(), status_code=500)


# Include additional API routes
app.include_router(router)


# ─────────────────────────────────────────────
# Background Monitoring Tasks (Infrastructure Only)
# ─────────────────────────────────────────────
async def heartbeat_snapshot():
    while True:
        await asyncio.sleep(60)
        try:
            store.write(
                [{
                    "domain": "system",
                    "metric": "heartbeat",
                    "value": 0,
                }],
                confidence=1.0,
            )
        except Exception:
            log.warning("[HEARTBEAT_WRITE_FAILED]")


async def monitoring_loop():
    monitor = TemporalMonitor()

    while True:
        await asyncio.sleep(21600)  # 6 hours

        try:
            domains = store.get_domains()
            for domain in domains:
                if domain != "system":
                    monitor.run_for_domain(domain)
        except Exception as e:
            log.error(f"[MONITORING_ERROR] {str(e)}")


@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    asyncio.create_task(heartbeat_snapshot())
    asyncio.create_task(monitoring_loop())


# ─────────────────────────────────────────────
# Stateless Ingestion Endpoint
# ─────────────────────────────────────────────
@app.post("/ingest/{port}")
async def ingest(port: str, request: Request):

    payload = await request.json()

    # Create fresh isolated organism state
    state = {
        "physics": {},
        "system_logs": [],
        "intelligence": {},
    }

    # Audit ingestion
    audit.log(payload, [], port, "API_INGEST")

    # Route through gateway
    if port == "sales":
        gateway.ingest_sales(payload, state, state["physics"])
    elif port == "ops":
        gateway.ingest_ops(payload, state, state["physics"])
    elif port == "finance":
        gateway.ingest_accounting(payload, state, state["physics"])
    elif port == "hr":
        gateway.ingest_hr(payload, state, state["physics"])
    elif port == "logistics":
        gateway.ingest_logistics(payload, state, state["physics"])
    else:
        return {"status": "unknown_port"}

    # Deterministic execution
    intelligence = kernel.run(state)

    return {
        "status": "processed",
        "port": port,
        "intelligence": intelligence,
    }


# ─────────────────────────────────────────────
# Monitoring Endpoint
# ─────────────────────────────────────────────
@app.get("/monitor/{domain}")
def get_monitoring(domain: str):
    return store.get_monitoring_timeline(domain)


# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "AEGIS_ALIVE"}
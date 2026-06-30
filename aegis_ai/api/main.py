# aegis_ai/api/main.py

import asyncio
import logging
from pathlib import Path

import anyio

# Load .env BEFORE importing app modules so OllamaProvider/etc. read fresh values.
# override=True so .env wins over stale persistent OS env vars (e.g. an older
# AEGIS_OLLAMA_MODEL pointing at a model that isn't installed).
try:
    from dotenv import load_dotenv
    _ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE, override=True)
except ImportError:
    pass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
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
    title="AEGIS — Enterprise Decision Intelligence",
    description="Deterministic behavioral intelligence for enterprise data.",
    version="2.1.0",
    debug=False,
    middleware=middleware,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─────────────────────────────────────────────
# CORS — Allow Next.js frontend
# ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
# Global Exception Handler — SECURE
# Never leaks stack traces to clients
# ─────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(
        f"[UNHANDLED_EXCEPTION] {request.method} {request.url.path} "
        f"— {type(exc).__name__}: {str(exc)}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "status": "ERROR"},
    )


# ─────────────────────────────────────────────
# Include API routes
# ─────────────────────────────────────────────
app.include_router(router)


# ─────────────────────────────────────────────
# Background Tasks
# ─────────────────────────────────────────────
async def heartbeat_snapshot():
    """Writes a heartbeat event every 60s to keep EventStore alive."""
    while True:
        await asyncio.sleep(60)
        try:
            store.write(
                tenant="system",
                events=[{
                    "domain": "system",
                    "metric": "heartbeat",
                    "value": 0,
                }],
                confidence=1.0,
            )
        except Exception as e:
            log.warning(f"[HEARTBEAT_WRITE_FAILED] {e}")


async def monitoring_loop():
    """Runs regime detection every 6 hours across all domains."""
    monitor = TemporalMonitor()

    while True:
        await asyncio.sleep(21600)  # 6 hours

        try:
            domains = store.get_domains()
            for domain in domains:
                if domain != "system":
                    monitor.run_for_domain(domain)
        except Exception as e:
            log.error(f"[MONITORING_ERROR] {str(e)}", exc_info=True)


# ─────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────
async def _llm_warmup_background():
    """
    Pre-load the local LLM into RAM so the first /chat request hits a warm
    model instead of paying a 90-180s cold-load. Fire-and-forget; the chat
    endpoint also has its own keyword-fallback so this is best-effort.
    """
    try:
        from aegis_ai.llm.call_gemma import warmup_gemma
        # Run the blocking HTTP call off the event loop.
        result = await anyio.to_thread.run_sync(warmup_gemma)
        if result.get("ok"):
            log.info(
                f"[LLM_WARMUP] model={result.get('model')} "
                f"loaded={result.get('loaded')} elapsed_ms={result.get('elapsed_ms')}"
            )
        else:
            log.warning(f"[LLM_WARMUP] failed: {result.get('error')}")
    except Exception as e:
        log.warning(f"[LLM_WARMUP] exception: {e}")


@app.on_event("startup")
async def startup():
    log.info("[AEGIS] Starting up...")
    Base.metadata.create_all(bind=engine)
    asyncio.create_task(heartbeat_snapshot())
    asyncio.create_task(monitoring_loop())
    asyncio.create_task(_llm_warmup_background())
    log.info("[AEGIS] Ready.")


# ─────────────────────────────────────────────
# Stateless Ingestion Endpoint (JSON/webhook path)
# ─────────────────────────────────────────────
@app.post("/ingest/{port}")
async def ingest(port: str, request: Request):

    payload = await request.json()
    tenant_id = str((request.scope.get("aegis.tenant") or {}).get("id") or "system")

    state = {
        "physics": {},
        "system_logs": [],
        "intelligence": {},
        "tenant_id": tenant_id,
    }

    audit.log(payload, [], port, "API_INGEST")

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
        return {"status": "unknown_port", "port": port}

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
# Health + Readiness
# ─────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "AEGIS_ALIVE", "version": "2.1.0"}


@app.get("/ready")
def ready():
    """Readiness probe — checks DB is accessible."""
    try:
        store.db.execute("SELECT 1")
        return {"status": "READY"}
    except Exception as e:
        log.error(f"[READINESS_FAIL] {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "NOT_READY", "detail": str(e)},
        )

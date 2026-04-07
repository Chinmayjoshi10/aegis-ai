from aegis_ai.connectors.csv_adapter import CSVAdapter
from aegis_ai.connectors.webhook_adapter import WebhookAdapter
from aegis_ai.connectors.accounting_adapter import AccountingAdapter
from aegis_ai.connectors.hr_adapter import HRAdapter
from aegis_ai.connectors.ops_adapter import OpsAdapter
from aegis_ai.connectors.sales_adapter import SalesAdapter
from aegis_ai.connectors.logistics_adapter import LogisticsAdapter


class EnterpriseGateway:
    """
    Master Nervous Gateway for AEGIS
    All real-world enterprise ports converge here.
    """

    def __init__(self):
        self.csv = CSVAdapter()
        self.webhook = WebhookAdapter()
        self.accounting = AccountingAdapter()
        self.hr = HRAdapter()
        self.ops = OpsAdapter()
        self.sales = SalesAdapter()
        self.logistics = LogisticsAdapter()

    # ─────────────── Batch / Legacy Ports ───────────────
    def ingest_csv(self, path, mapping, state, physics_state, confidence=1.0):
        self.csv.ingest(path, mapping, state, physics_state, confidence=confidence)

    # ─────────────── Live Streaming Ports ───────────────
    def ingest_webhook(self, payload, mapping, state, physics_state, confidence=0.9):
        self.webhook.ingest(payload, mapping, state, physics_state, confidence=confidence)

    # ─────────────── Financial Nervous Port ─────────────
    def ingest_accounting(self, payload, state, physics_state, confidence=0.95):
        self.accounting.ingest(payload, state, physics_state, confidence=confidence)

    # ─────────────── Workforce Nervous Port ─────────────
    def ingest_hr(self, payload, state, physics_state, confidence=0.9):
        self.hr.ingest(payload, state, physics_state, confidence=confidence)

    # ─────────────── Production Nervous Port ────────────
    def ingest_ops(self, payload, state, physics_state, confidence=0.9):
        self.ops.ingest(payload, state, physics_state, confidence=confidence)

    # ─────────────── Market Nervous Port ────────────────
    def ingest_sales(self, payload, state, physics_state, confidence=0.9):
        self.sales.ingest(payload, state, physics_state, confidence=confidence)

    # ─────────────── Supply Chain Nervous Port ──────────
    def ingest_logistics(self, payload, state, physics_state, confidence=0.9):
        self.logistics.ingest(payload, state, physics_state, confidence=confidence)

    # ─────────────────────────────────────────────────────
    # UNIFIED ROUTE EVENT (FOR TEMPORAL REPLAY)
    # ─────────────────────────────────────────────────────
    def route_event(self, domain, metric, value, confidence, state, physics):

        payload = {
            "domain": domain,
            "metric": metric,
            "value": value,
        }

        if domain == "sales":
            self.ingest_sales(payload, state, physics, confidence=confidence)

        elif domain == "ops":
            self.ingest_ops(payload, state, physics, confidence=confidence)

        elif domain == "finance":
            self.ingest_accounting(payload, state, physics, confidence=confidence)

        elif domain == "hr":
            self.ingest_hr(payload, state, physics, confidence=confidence)

        elif domain == "logistics":
            self.ingest_logistics(payload, state, physics, confidence=confidence)

        else:
            # Unknown domain — ignore safely
            state.setdefault("system_logs", []).append(
                f"[ROUTE_EVENT_WARNING] Unknown domain: {domain}"
            )

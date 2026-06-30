from aegis_ai.spine.lineage_audit import LineageAudit
from aegis_ai.spine.event_store import EventStore
from aegis_ai.connectors.universal_adapter import UniversalAdapter


class AccountingAdapter:
    """
    High-Fidelity Financial Nervous Port for AEGIS
    Maps enterprise Potential Energy (liquidity & pressure) safely.
    """

    def __init__(self):
        self.adapter = UniversalAdapter()
        self.audit = LineageAudit()
        self.store = EventStore()

    def ingest(self, payload: dict, state: dict, physics_state: dict,
               source="accounting", confidence=0.95):
        """
        payload example:
        {
            "cash_balance": 120000,
            "receivables": 45000,
            "payables": 38000,
            "expenses_today": 3400,
            "revenue_today": 8900
        }
        """

        # ─────────────────────────────────────────────
        # Internal consistency validation
        # ─────────────────────────────────────────────
        try:
            cash = float(payload.get("cash_balance", 0))
            receivables = float(payload.get("receivables", 0))
            payables = float(payload.get("payables", 0))
            expenses = float(payload.get("expenses_today", 0))
            revenue = float(payload.get("revenue_today", 0))
        except Exception:
            self.audit.log(payload, [], source, "ACCOUNTING_INVALID_SCHEMA")
            return

        # ─────────────────────────────────────────────
        # Zero-Cash Guardrail (Systemic Insolvency)
        # ─────────────────────────────────────────────
        if cash <= 0:
            state.setdefault("risk_events", []).append({
                "type": "SYSTEMIC_INSOLVENCY",
                "cash_balance": cash
            })
            self.audit.log(payload, [], source, "SYSTEMIC_INSOLVENCY")
            return

        # ─────────────────────────────────────────────
        # Canonical Physics Mapping
        # Liquid vs Non-Liquid
        mapping = {
            "cash_balance": [("finance", "cash_reserve")],          # LIQUID
            "receivables": [("finance", "non_liquid_assets")],     # NON-LIQUID

            # Pressure vs Flow
            "payables": [("finance", "structural_pressure")],      # PRESSURE
            "expenses_today": [("finance", "burn_rate")],          # FLOW
            "revenue_today": [("sales", "flow_rate")]
        }

        # Forensic trace
        self.audit.log(payload, [], source, "ACCOUNTING_EVENT")

        # Ground-truth commit for runway decay d(Cash)/dt
        self.store.write(
            tenant=str(state.get("tenant_id") or "system"),
            events=[{"domain": "finance", "metric": "cash_reserve", "value": cash}],
            confidence=confidence
        )

        # Inject into organism
        self.adapter.inject(
            physics_state=physics_state,
            rows=[payload],
            mapping=mapping,
            source=source,
            confidence=confidence
        )

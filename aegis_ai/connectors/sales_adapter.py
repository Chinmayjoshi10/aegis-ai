from aegis_ai.spine.lineage_audit import LineageAudit
from aegis_ai.spine.event_store import EventStore
from aegis_ai.connectors.universal_adapter import UniversalAdapter


class SalesAdapter:
    """
    Market Energy Nervous Port for AEGIS
    Models pressure, kinetic inflow velocity, friction, and ops backpressure.
    """

    def __init__(self):
        self.adapter = UniversalAdapter()
        self.audit = LineageAudit()
        self.store = EventStore()

    def ingest(self, payload: dict, state: dict, physics_state: dict,
               source="sales", confidence=0.9):
        """
        payload example:
        {
            "new_leads": 340,
            "lost_leads": 55,
            "conversion_rate": 0.12,
            "revenue_today": 8900,
            "refunds_today": 1200
        }
        """

        # ─────────────────────────────────────────────
        # Schema validation
        # ─────────────────────────────────────────────
        try:
            leads = float(payload.get("new_leads", 0))
            lost = float(payload.get("lost_leads", 0))
            conv = float(payload.get("conversion_rate", 0))
            revenue = float(payload.get("revenue_today", 0))
            refunds = float(payload.get("refunds_today", 0))
        except Exception:
            self.audit.log(payload, [], source, "SALES_INVALID_SCHEMA")
            return

        # ─────────────────────────────────────────────
        # Balance check (anti-sensor-noise)
        # ─────────────────────────────────────────────
        if revenue > 0 and (leads <= 0 or conv <= 0):
            state.setdefault("risk_events", []).append({
                "type": "SALES_DATA_ANOMALY",
                "reason": "Revenue without lead/conv support"
            })
            self.audit.log(payload, [], source, "SALES_DATA_ANOMALY")
            return

        # ─────────────────────────────────────────────
        # Market physics
        # ─────────────────────────────────────────────
        # Potential pressure (demand head)
        potential_pressure = max(0.0, leads)

        # Flow from pressure
        flow_rate = potential_pressure * max(0.0, conv)

        # Market friction (leaks & refunds)
        market_friction = max(0.0, lost + refunds)

        # Kinetic inflow velocity of money
        inflow_velocity = max(0.0, revenue)

        # ─────────────────────────────────────────────
        # Canonical mapping (multi-domain coupling)
        # ─────────────────────────────────────────────
        mapping = {
            # Pressure & flow
            "_pressure": [("sales", "potential_pressure")],
            "_flow": [
                ("sales", "flow_rate"),
                ("ops", "fatigue")   # ops backpressure coupling
            ],
            # Friction
            "_friction": [("sales", "market_friction")],
            # Money as kinetic inflow (not static)
            "_inflow_velocity": [("finance", "inflow_velocity")]
        }

        synthetic = {
            "_pressure": potential_pressure,
            "_flow": flow_rate,
            "_friction": market_friction,
            "_inflow_velocity": inflow_velocity
        }

        # ─────────────────────────────────────────────
        # Forensic trace
        # ─────────────────────────────────────────────
        self.audit.log(payload, [], source, "SALES_MARKET_EVENT")

        # ─────────────────────────────────────────────
        # Ground truth memory
        # ─────────────────────────────────────────────
        self.store.write(
            tenant=str(state.get("tenant_id") or "system"),
            events=[
                {"domain": "sales", "metric": "flow_rate", "value": flow_rate},
                {"domain": "finance", "metric": "inflow_velocity", "value": inflow_velocity}
            ],
            confidence=confidence
        )

        # ─────────────────────────────────────────────
        # Inject into organism
        # ─────────────────────────────────────────────
        self.adapter.inject(
            physics_state=physics_state,
            rows=[synthetic],
            mapping=mapping,
            source=source,
            confidence=confidence
        )

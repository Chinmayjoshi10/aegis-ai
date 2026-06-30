from aegis_ai.spine.lineage_audit import LineageAudit
from aegis_ai.spine.event_store import EventStore
from aegis_ai.connectors.universal_adapter import UniversalAdapter


class LogisticsAdapter:
    """
    Supply Chain Impedance Circuit for AEGIS
    Models impedance, reverse work, and flow health damping.
    """

    def __init__(self):
        self.adapter = UniversalAdapter()
        self.audit = LineageAudit()
        self.store = EventStore()

    def ingest(self, payload: dict, state: dict, physics_state: dict,
               source="logistics", confidence=0.9):
        """
        payload example:
        {
            "avg_delivery_delay_hours": 48,
            "shipments_delayed": 7,
            "returns_today": 18,
            "inventory_units": 2400
        }
        """

        # ─────────────────────────────────────────────
        # Schema validation
        # ─────────────────────────────────────────────
        try:
            delay = float(payload.get("avg_delivery_delay_hours", 0))
            delayed = float(payload.get("shipments_delayed", 0))
            returns = float(payload.get("returns_today", 0))
            inventory = float(payload.get("inventory_units", 0))
        except Exception:
            self.audit.log(payload, [], source, "LOGISTICS_INVALID_SCHEMA")
            return

        # ─────────────────────────────────────────────
        # Impedance & reverse work coefficients
        # ─────────────────────────────────────────────
        systemic_impedance = (delay / max(1.0, inventory)) + (delayed / max(1.0, inventory))
        reverse_work = returns / max(1.0, inventory)

        # Flow health index (0 = dead artery, 1 = free flow)
        flow_health = max(0.0, 1.0 - systemic_impedance)

        # ─────────────────────────────────────────────
        # Canonical physics mapping
        # ─────────────────────────────────────────────
        mapping = {
            "_impedance": [
                ("logistics", "systemic_impedance"),
                ("sales", "max_flow_drag")     # throttles SalesBrain velocity
            ],
            "_reverse_work": [
                ("ops", "reverse_work"),       # consumes ops capacity
            ],
            "_flow_health": [
                ("finance", "flow_health")     # revenue damping factor
            ]
        }

        synthetic = {
            "_impedance": systemic_impedance,
            "_reverse_work": reverse_work,
            "_flow_health": flow_health
        }

        # ─────────────────────────────────────────────
        # Forensic trace
        # ─────────────────────────────────────────────
        self.audit.log(payload, [], source, "LOGISTICS_IMPEDANCE_EVENT")

        # ─────────────────────────────────────────────
        # Ground truth decay memory
        # ─────────────────────────────────────────────
        self.store.write(
            tenant=str(state.get("tenant_id") or "system"),
            events=[{"domain": "logistics", "metric": "inventory_units", "value": inventory}],
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

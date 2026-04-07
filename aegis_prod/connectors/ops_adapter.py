from aegis_ai.spine.lineage_audit import LineageAudit
from aegis_ai.spine.event_store import EventStore
from aegis_ai.connectors.universal_adapter import UniversalAdapter

class OpsAdapter:
    """
    Industrial Fluid-Dynamics Nervous Port for AEGIS
    Models viscosity, backpressure, entropy, and conservation of work.
    """

    def __init__(self):
        self.adapter = UniversalAdapter()
        self.audit = LineageAudit()
        self.store = EventStore()

    def ingest(self, payload: dict, state: dict, physics_state: dict,
               source="ops", confidence=0.9):
        """
        payload example:
        {
            "units_produced": 820,
            "units_backlog": 340,
            "avg_delay_hours": 12,
            "defect_rate": 0.03,
            "machine_downtime_hours": 6
        }
        """

        # ─────────────────────────────────────────────
        # Schema validation
        # ─────────────────────────────────────────────
        try:
            produced = float(payload.get("units_produced", 0))
            backlog = float(payload.get("units_backlog", 0))
            delay = float(payload.get("avg_delay_hours", 0))
            defect = float(payload.get("defect_rate", 0))
            downtime = float(payload.get("machine_downtime_hours", 0))
        except Exception:
            self.audit.log(payload, [], source, "OPS_INVALID_SCHEMA")
            return

        # ─────────────────────────────────────────────
        # Conservation of Work (ΔBacklog vs Throughput)
        # If backlog drops sharply without throughput rising → cancel/adjust
        # ─────────────────────────────────────────────
        last_backlog = state.get("last_ops_backlog", None)
        if last_backlog is not None:
            delta_backlog = backlog - last_backlog
            if delta_backlog < 0 and produced <= 0:
                # Backlog went down but no throughput → must be cancellations; log entropy spike
                self.audit.log(payload, [], source, "OPS_CONSERVATION_ALERT")
        state["last_ops_backlog"] = backlog

        # ─────────────────────────────────────────────
        # Fluid dynamics transformations
        # ─────────────────────────────────────────────
        # Viscosity (systemic drag)
        systemic_viscosity = max(0.0, downtime)

        # Structural backpressure (pressure in pipes)
        structural_pressure = max(0.0, backlog)

        # Entropy (energy loss) → reduces effective yield
        entropy_loss = max(0.0, min(1.0, defect))

        # Effective yield after entropy
        effective_yield = produced * (1.0 - entropy_loss)

        # ─────────────────────────────────────────────
        # Canonical Physics Mapping (multi-domain effects)
        # ─────────────────────────────────────────────
        mapping = {
            # Flow & fatigue
            "_effective_yield": [("ops", "throughput")],
            "_structural_pressure": [
                ("ops", "fatigue"),           # ops fatigue
                ("hr", "burnout_pressure"),   # HR heat via backpressure
                ("finance", "burn_rate")      # overtime cost pressure
            ],
            # Viscosity → global drag
            "_systemic_viscosity": [
                ("ops", "systemic_viscosity"),
                ("sales", "max_flow_drag")    # limits SalesBrain max flow
            ],
            # Logistics drag
            "avg_delay_hours": [("logistics", "blockage")],
            # Entropy
            "_entropy_loss": [("ops", "entropy")]
        }

        synthetic = {
            "_effective_yield": effective_yield,
            "_structural_pressure": structural_pressure,
            "_systemic_viscosity": systemic_viscosity,
            "_entropy_loss": entropy_loss,
            "avg_delay_hours": delay
        }

        # ─────────────────────────────────────────────
        # Forensic trace
        # ─────────────────────────────────────────────
        self.audit.log(payload, [], source, "OPS_FLUID_EVENT")

        # ─────────────────────────────────────────────
        # Ground truth memory for decay & coupling
        # ─────────────────────────────────────────────
        self.store.write(
            [
                {"domain": "ops", "metric": "throughput", "value": effective_yield},
                {"domain": "ops", "metric": "systemic_viscosity", "value": systemic_viscosity},
                {"domain": "ops", "metric": "entropy", "value": entropy_loss}
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

from aegis_ai.spine.lineage_audit import LineageAudit
from aegis_ai.spine.event_store import EventStore
from aegis_ai.connectors.universal_adapter import UniversalAdapter

class HRAdapter:
    """
    Workforce Thermal Physics Port for AEGIS
    Humans are modeled as a thermal + impedance system.
    """

    ATTRITION_BREACH_THRESHOLD = 0.05   # 5% structural loss per cycle

    def __init__(self):
        self.adapter = UniversalAdapter()
        self.audit = LineageAudit()
        self.store = EventStore()

    def ingest(self, payload: dict, state: dict, physics_state: dict,
               source="hr", confidence=0.9):
        """
        payload example:
        {
            "active_employees": 120,
            "employees_left_today": 2,
            "open_positions": 6,
            "overtime_hours": 180,
            "sick_leaves_today": 4
        }
        """

        # ─────────────────────────────────────────────
        # Schema + thermal mass
        # ─────────────────────────────────────────────
        try:
            active = float(payload.get("active_employees", 0))
            left = float(payload.get("employees_left_today", 0))
            open_pos = float(payload.get("open_positions", 0))
            overtime = float(payload.get("overtime_hours", 0))
            sick = float(payload.get("sick_leaves_today", 0))
        except Exception:
            self.audit.log(payload, [], source, "HR_INVALID_SCHEMA")
            return

        if active <= 0:
            self.audit.log(payload, [], source, "HR_ZERO_WORKFORCE")
            return

        # ─────────────────────────────────────────────
        # Thermal Normalization
        # ─────────────────────────────────────────────
        burnout_heat = (overtime + sick) / active          # normalized heat
        structural_attrition = left / active               # structural loss ratio
        systemic_impedance = open_pos / active             # impedance ratio

        # ─────────────────────────────────────────────
        # Integrity Breach Guardrail
        # ─────────────────────────────────────────────
        if structural_attrition >= self.ATTRITION_BREACH_THRESHOLD:
            state.setdefault("risk_events", []).append({
                "type": "HR_INTEGRITY_BREACH",
                "attrition_ratio": structural_attrition
            })
            self.audit.log(payload, [], source, "HR_INTEGRITY_BREACH")
            return

        # ─────────────────────────────────────────────
        # Canonical Physics Mapping
        # ─────────────────────────────────────────────
        mapping = {
            "active_employees": [("ops", "throughput")],
            # Heat & fatigue
            "_burnout_heat": [("hr", "burnout_pressure")],
            # Structural impedance
            "_impedance": [("ops", "systemic_impedance")],
            # Attrition decay
            "_attrition": [("hr", "attrition_rate")]
        }

        # Inject normalized synthetic signals
        synthetic_row = {
            "_burnout_heat": burnout_heat,
            "_impedance": systemic_impedance,
            "_attrition": structural_attrition,
            "active_employees": active
        }

        # Forensic trace
        self.audit.log(payload, [], source, "HR_THERMAL_EVENT")

        # Ground truth store for cooling-rate / drift learning
        self.store.write(
            tenant=str(state.get("tenant_id") or "system"),
            events=[
                {"domain": "hr", "metric": "burnout_pressure", "value": burnout_heat},
                {"domain": "ops", "metric": "systemic_impedance", "value": systemic_impedance},
                {"domain": "hr", "metric": "attrition_rate", "value": structural_attrition}
            ],
            confidence=confidence
        )

        # Inject into organism
        self.adapter.inject(
            physics_state=physics_state,
            rows=[synthetic_row],
            mapping=mapping,
            source=source,
            confidence=confidence
        )

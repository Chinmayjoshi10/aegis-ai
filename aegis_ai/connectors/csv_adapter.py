import pandas as pd
import math
from aegis_ai.connectors.universal_adapter import UniversalAdapter
from aegis_ai.spine.lineage_audit import LineageAudit


class CSVAdapter:
    """
    Hardened Enterprise CSV Gateway for AEGIS.
    """

    CRITICAL_FIELDS = {"value"}   # must never be NaN / None

    def __init__(self):
        self.adapter = UniversalAdapter()
        self.audit = LineageAudit()

    # ─────────────────────────────────────────────
    # SAFE INGEST
    # ─────────────────────────────────────────────
    def ingest(self, csv_path, mapping, state, physics_state, source="csv", confidence=1.0, chunk_size=1000):

        # Ensure system log exists
        state.setdefault("system_logs", [])

        # ── File safety
        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            state.setdefault("risk_events", []).append({
                "type": "CSV_READ_FAILURE",
                "file": csv_path,
                "error": str(e)
            })
            return

        # ── Schema enforcement
        for raw_key in mapping.keys():
            if raw_key not in df.columns:
                state.setdefault("risk_events", []).append({
                    "type": "CSV_SCHEMA_VIOLATION",
                    "file": csv_path,
                    "missing_column": raw_key
                })
                return

        total_rows = len(df)
        if total_rows == 0:
            return

        chunks = math.ceil(total_rows / chunk_size)

        # ── Permanent forensic record
        self.audit.log(
            raw_payload={"file": csv_path, "rows": total_rows},
            normalized_events=[],
            source=source,
            reason_code="CSV_INGEST_START"
        )

        for i in range(chunks):
            start = i * chunk_size
            end = min(start + chunk_size, total_rows)
            part = df.iloc[start:end].to_dict(orient="records")

            state["system_logs"].append(f"Ingestion Progress: Chunk {i+1}/{chunks}")

            # Filter dirty rows (NaN / None)
            clean_rows = []
            for r in part:
                bad = False
                for raw_key in mapping.keys():
                    v = r.get(raw_key)
                    if v is None or (isinstance(v, float) and math.isnan(v)):
                        bad = True
                        break
                if not bad:
                    clean_rows.append(r)

            # Inject into organism
            if clean_rows:
                self.adapter.inject(
                    physics_state=physics_state,
                    rows=clean_rows,
                    mapping=mapping,
                    source=source,
                    confidence=confidence
                )

        # Final forensic close
        self.audit.log(
            raw_payload={"file": csv_path, "rows": total_rows},
            normalized_events=[],
            source=source,
            reason_code="CSV_INGEST_COMPLETE"
        )

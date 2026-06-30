from typing import List, Dict, Any
from datetime import datetime

from aegis_ai.db.session import SessionLocal
from aegis_ai.db.models.insight_ledger import InsightLedger


class DecisionPersistenceService:
    """
    Responsible for storing synthesized decisions into InsightLedger
    """

    def __init__(self):
        self.db = SessionLocal()

    def store(self, tenant_id: str, decisions: List[Dict[str, Any]]) -> int:
        if not decisions:
            return 0

        records = []

        for d in decisions:
            record = InsightLedger(
                tenant_id=tenant_id,
                decision_type=d.get("type"),
                decision_text=d.get("decision"),
                confidence=d.get("confidence"),
                impact=d.get("impact"),
                signals=",".join(d.get("signals", [])),
                created_at=datetime.utcnow()
            )
            records.append(record)

        try:
            self.db.add_all(records)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

        return len(records)

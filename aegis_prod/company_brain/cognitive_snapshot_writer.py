# aegis_ai/company_brain/cognitive_snapshot_writer.py

import uuid
from datetime import datetime


def build_cognitive_snapshot(
    *,
    tenant: str,
    brain_name: str,
    model_version: str,
    health_score: float,
    snapshot_blob: dict,
) -> dict:
    """
    Pure cognitive snapshot builder.

    No DB.
    No ORM.
    No side effects.
    """

    return {
        "tenant": tenant,
        "snapshot_id": str(uuid.uuid4()),
        "brain_name": brain_name,
        "model_version": model_version,
        "health_score": health_score,
        "snapshot_blob": snapshot_blob,
        "created_at": datetime.utcnow(),
    }
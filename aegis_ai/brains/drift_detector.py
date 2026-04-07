from sqlalchemy.orm import Session

from aegis_ai.db.baselines.persistence import (
    get_last_baseline,
    persist_drift_event,
)

class DriftDetector:
    """
    Production-ready drift detector that compares:
    current upload vs LAST STORED BASELINE in Postgres.
    """

    def detect_and_store(
        self,
        session: Session,
        tenant: str,
        domain: str,
        current_stats: dict,
        sigma_threshold: float = 2.0,
    ):
        """
        - Loads last baseline from DB
        - Computes drift
        - Stores drift event in Postgres
        - Returns structured report
        """

        report = {}

        for category, columns in current_stats.items():

            if category not in report:
                report[category] = {}

            for col, curr in columns.items():

                base = get_last_baseline(
                    session=session,
                    tenant=tenant,
                    domain=domain,
                    category=category,
                    column=col,
                )

                # If no baseline exists, we cannot compute drift
                if base is None:
                    report[category][col] = {
                        "status": "NO_BASELINE",
                        "message": "First observation; baseline created."
                    }
                    continue

                # Compute scale drift
                mean_diff = abs(curr["mean"] - base.mean)
                allowed_band = sigma_threshold * (base.std or 1e-6)

                drift_score = mean_diff / (allowed_band + 1e-6)

                if base.std == 0:
                    drift_type = "zero_variance_baseline"
                    alert = True

                elif mean_diff > allowed_band:
                    drift_type = "scale_shift"
                    alert = True

                elif curr["null_ratio"] > base.null_ratio * 1.5:
                    drift_type = "missing_shift"
                    alert = True

                else:
                    drift_type = "stable"
                    alert = False

                # Persist drift event
                persist_drift_event(
                    session=session,
                    tenant=tenant,
                    domain=domain,
                    category=category,
                    column=col,
                    baseline_date=base.upload_date,
                    drift_score=float(drift_score),
                    drift_type=drift_type,
                    alert=alert,
                )

                report[category][col] = {
                    "status": "DRIFT_DETECTED" if alert else "STABLE",
                    "drift_type": drift_type,
                    "drift_score": float(drift_score),
                    "baseline_mean": base.mean,
                    "current_mean": curr["mean"],
                }

        return report

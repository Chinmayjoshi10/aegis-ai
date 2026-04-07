class QualityGate:
    """
    QualityGate evaluates DATA FITNESS using RealityReader statistics.

    HARD RULE:
    - QualityGate NEVER recomputes statistics
    - RealityReader is the ONLY numeric authority
    """

    def assess(self, numeric_stats: dict) -> dict:
        report = {
            "overall_status": "OK",

            "monitoring_ready": True,
            "drift_ready": True,
            "forecast_ready": True,

            # NORMAL | ROBUST | BASELINE | PAUSED
            "forecast_mode": "NORMAL",

            "missing_pct": {},
            "outliers": {},
            "notes": [],
            "forecast_block_reasons": [],
        }

        if not numeric_stats:
            report["overall_status"] = "BLOCKED"
            report["monitoring_ready"] = False
            report["drift_ready"] = False
            report["forecast_ready"] = False
            report["forecast_mode"] = "PAUSED"
            report["notes"].append("No numeric statistics available")
            report["forecast_block_reasons"].append("No numeric data")
            return report

        total_rows = None
        max_outlier_ratio = 0.0
        high_missing_cols = 0

        # -----------------------------
        # Inspect RealityReader stats
        # -----------------------------
        for col, stats in numeric_stats.items():
            count = stats.get("count", 0)
            null_ratio = stats.get("null_ratio", 0.0)
            outlier_count = stats.get("three_sigma_outliers", 0)

            report["missing_pct"][col] = round(null_ratio, 4)
            report["outliers"][col] = int(outlier_count)

            if null_ratio > 0.4:
                high_missing_cols += 1
                report["notes"].append(
                    f"{col}: high missing ratio ({null_ratio:.2%})"
                )

            if count > 0:
                ratio = outlier_count / count
                max_outlier_ratio = max(max_outlier_ratio, ratio)

            total_rows = count if total_rows is None else total_rows

        # -----------------------------
        # Forecast decision ladder
        # -----------------------------

        # 🔴 PAUSED — structurally unsafe
        if high_missing_cols / max(len(numeric_stats), 1) > 0.4:
            report["forecast_ready"] = False
            report["forecast_mode"] = "PAUSED"
            report["forecast_block_reasons"].append(
                "Severe missing data across columns"
            )

        # 🟠 BASELINE — extreme volatility
        elif max_outlier_ratio > 0.10:
            report["forecast_mode"] = "BASELINE"
            report["forecast_block_reasons"].append(
                f"Extreme volatility in at least one column (~{max_outlier_ratio*100:.1f}% rows affected)"
            )

        # 🟡 ROBUST — moderate volatility
        elif max_outlier_ratio > 0.03:
            report["forecast_mode"] = "ROBUST"
            report["forecast_block_reasons"].append(
                f"Moderate volatility detected (~{max_outlier_ratio*100:.1f}% rows affected)"
            )

        # 🟢 NORMAL — clean
        else:
            report["forecast_mode"] = "NORMAL"

        # -----------------------------
        # Overall UI status
        # -----------------------------
        if report["forecast_mode"] in {"ROBUST", "BASELINE"}:
            report["overall_status"] = "LIMITED"

        if report["forecast_mode"] == "PAUSED":
            report["overall_status"] = "BLOCKED"

        return report

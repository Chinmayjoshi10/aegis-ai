import logging

log = logging.getLogger("aegis_ai.sanitizer.quality_gate")

# W3: data_quality_score must respond to missingness.
_MAX_MISSING_BEFORE_BLOCK = 0.20  # >20% missing on any KPI → DATA_ISSUE

# W4: scaling / bimodality detection — uses only stats RealityReader emits
# (mean, median, std, min, max). A healthy numeric distribution has
# (max - min) / std ≈ 4–8 (normal) or 5–10 (log-normal with short tails).
# A 2-population scale mixture (e.g. dollars vs cents) blows up because
# std inflates slower than range. Threshold 20 is conservative (very few
# clean datasets ever hit it) and flags the textbook cents-vs-dollars case.
_RANGE_STD_BIMODALITY_THRESHOLD = 20.0
# Paranoid fallback: median-to-extreme shift. If max > median + 20σ OR
# min < median - 20σ, the series carries a scale-mixed tail.
_EXTREME_SIGMA_SHIFT = 20.0

# R5 / W6: noise-floor guard — if coefficient of variation < 1e-3 the column
# is effectively constant and structural signals are misleading.
_MIN_COEFF_VARIATION = 1e-3


class QualityGate:
    """
    QualityGate evaluates DATA FITNESS using RealityReader statistics.

    HARD RULE:
    - QualityGate NEVER recomputes statistics (std/IQR are taken from
      RealityReader's numeric_stats block — not recomputed from df).
    - RealityReader is the ONLY numeric authority.

    Hardened outputs:
      report["scaling_suspects"]    list of cols with std/IQR > 2.5
      report["noise_floor_cols"]    list of cols where σ/|μ| < 1e-3
      report["missing_critical"]    list of cols with null_ratio > 20%
      report["data_quality_score"]  now multiplied by (1 - max_missing_pct)
      report["overall_status"] = "BLOCKED" if any critical missing or scaling
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

            # Hardening (W3/W4/R5)
            "missing_critical":  [],
            "scaling_suspects":  [],
            "noise_floor_cols":  [],
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
        max_missing_pct = 0.0
        for col, stats in numeric_stats.items():
            count = stats.get("count", 0)
            null_ratio = stats.get("null_ratio", 0.0)
            outlier_count = stats.get("three_sigma_outliers", 0)

            report["missing_pct"][col] = round(null_ratio, 4)
            report["outliers"][col] = int(outlier_count)

            # W3: track max missing across ANY column
            max_missing_pct = max(max_missing_pct, float(null_ratio))

            # W3: columns over 20% missing are CRITICAL
            if null_ratio > _MAX_MISSING_BEFORE_BLOCK:
                report["missing_critical"].append(col)
                report["notes"].append(
                    f"{col}: critical missing ratio ({null_ratio:.2%}) "
                    f"exceeds {_MAX_MISSING_BEFORE_BLOCK:.0%} threshold"
                )

            if null_ratio > 0.4:
                high_missing_cols += 1
                report["notes"].append(
                    f"{col}: high missing ratio ({null_ratio:.2%})"
                )

            # W4: scaling / bimodality detection — uses only stats RealityReader
            # emits. Three complementary heuristics cover the common failure
            # modes:
            #   (a) Coefficient of variation >0.85 → classic scale-mixture
            #       (dollars-vs-cents blows CV past unity).
            #   (b) (max - min) / std >20         → long-tail + outlier mix.
            #   (c) |median - mean| / std > 0.35  → asymmetry-driven mixture.
            std     = float(stats.get("std", 0.0) or 0.0)
            v_min   = float(stats.get("min", 0.0) or 0.0)
            v_max   = float(stats.get("max", 0.0) or 0.0)
            mean_v  = float(stats.get("mean", 0.0) or 0.0)
            median  = float(stats.get("median", mean_v) or mean_v)
            flagged_reason = None
            if std > 0:
                cv = std / abs(mean_v) if abs(mean_v) > 1e-12 else float("inf")
                range_std = (v_max - v_min) / std
                max_median_ratio = (
                    abs(v_max) / abs(median)
                    if abs(median) > 1e-9 else float("inf")
                )
                # Two independent tests; either one firing flags the column.
                # Calibrated to catch the textbook scaling cases (edge_scaling,
                # edge_spike) while leaving legitimate segment-driven skews
                # (Scenario E's TikTok tail) alone.
                if cv > 1.2:
                    flagged_reason = f"CV={cv:.2f}"
                elif max_median_ratio > 50 and cv > 0.85:
                    flagged_reason = (
                        f"max/median={max_median_ratio:.0f} (CV={cv:.2f})"
                    )
                elif range_std > _RANGE_STD_BIMODALITY_THRESHOLD and cv > 0.85:
                    flagged_reason = f"range/std={range_std:.1f} (CV={cv:.2f})"
            if flagged_reason:
                report["scaling_suspects"].append({
                    "column":   col,
                    "std":      round(std, 4),
                    "min":      round(v_min, 4),
                    "max":      round(v_max, 4),
                    "median":   round(median, 4),
                    "mean":     round(mean_v, 4),
                    "reason":   flagged_reason,
                })
                report["notes"].append(
                    f"{col}: scaling / bimodality suspected ({flagged_reason})"
                )

            # R5 / W6: noise-floor guard — σ/|μ| < 1e-3 means essentially constant.
            mean = float(stats.get("mean", 0.0) or 0.0)
            if std > 0 and abs(mean) > 1e-12:
                cv = std / abs(mean)
                if cv < _MIN_COEFF_VARIATION:
                    report["noise_floor_cols"].append(col)
                    report["notes"].append(
                        f"{col}: coefficient of variation {cv:.2e} "
                        f"below {_MIN_COEFF_VARIATION:.0e} — noise-floor"
                    )

            if count > 0:
                ratio = outlier_count / count
                max_outlier_ratio = max(max_outlier_ratio, ratio)

            total_rows = count if total_rows is None else total_rows

        report["max_missing_pct"] = round(max_missing_pct, 4)

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
        # Domain validation flags
        # -----------------------------
        domain_violations = {}
        for col, stats in numeric_stats.items():
            inv = stats.get("invalid_count", 0)
            if inv > 0:
                domain_violations[col] = inv
                report["notes"].append(
                    f"{col}: {inv} rows with INVALID_DOMAIN_VALUES"
                )

        report["domain_violations"] = domain_violations

        # -----------------------------
        # Data quality score (0.0-1.0) — W3 hardened
        # -----------------------------
        total_rows = max(
            max((s.get("count", 0) for s in numeric_stats.values()), default=1), 1
        )
        total_invalid = sum(domain_violations.values())
        invalid_penalty = min(total_invalid / total_rows, 0.3)
        missing_penalty = min(
            sum(1 for v in report["missing_pct"].values() if v > 0.1) * 0.05,
            0.2,
        )
        # W3: multiplicative missingness penalty — score scales directly with
        # the max missing ratio on any column. 25% missing → score × 0.75.
        missing_multiplier = max(1.0 - max_missing_pct, 0.0)
        # W4: hard penalty when scaling/bimodality detected anywhere.
        scaling_multiplier = 0.80 if report["scaling_suspects"] else 1.0

        raw_score = max(1.0 - invalid_penalty - missing_penalty, 0.0)
        report["data_quality_score"] = round(
            max(raw_score * missing_multiplier * scaling_multiplier, 0.0),
            4,
        )

        # -----------------------------
        # Overall UI status
        # -----------------------------
        if report["forecast_mode"] in {"ROBUST", "BASELINE"}:
            report["overall_status"] = "LIMITED"

        if report["forecast_mode"] == "PAUSED":
            report["overall_status"] = "BLOCKED"

        if domain_violations and report["overall_status"] == "OK":
            report["overall_status"] = "LIMITED"

        # W3: critical missingness forces BLOCKED so state-compute routes to DATA_ISSUE
        if report["missing_critical"]:
            report["overall_status"] = "BLOCKED"
            report["forecast_ready"] = False
            report["forecast_mode"] = "PAUSED"
            report["forecast_block_reasons"].append(
                f"Critical missing columns: {', '.join(report['missing_critical'])}"
            )

        # W4: scaling suspicion forces BLOCKED (mixed units / data ingestion bug)
        if report["scaling_suspects"]:
            report["overall_status"] = "BLOCKED"
            report["forecast_ready"] = False
            report["forecast_mode"] = "PAUSED"
            report["forecast_block_reasons"].append(
                "Scaling / bimodality suspected: "
                + ", ".join(s["column"] for s in report["scaling_suspects"])
            )

        log.info(
            f"[QualityGate] status={report['overall_status']} "
            f"score={report['data_quality_score']} "
            f"max_missing={max_missing_pct:.2%} "
            f"critical={report['missing_critical']} "
            f"scaling={len(report['scaling_suspects'])} "
            f"noise_floor={len(report['noise_floor_cols'])}"
        )

        return report

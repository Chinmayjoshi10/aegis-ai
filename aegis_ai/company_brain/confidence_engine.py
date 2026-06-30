import math
from typing import Optional, List


def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(value, max_value))


# ---------------------------------------------------------
# SAMPLE SIZE SCORE (MIU-aware)
# ---------------------------------------------------------
def compute_sample_size_score(
    *,
    row_count: int,
    miu_threshold: int = 1000,
    full_confidence_threshold: int = 10000,
) -> float:
    """
    Computes N_score based on cumulative data volume.

    < MIU          -> 0.0 (hard silence)
    MIU–10k        -> logarithmic ramp-up
    >= 10k         -> 1.0
    """

    if row_count < miu_threshold:
        return 0.0

    if row_count >= full_confidence_threshold:
        return 1.0

    return math.log10(row_count / miu_threshold) / math.log10(
        full_confidence_threshold / miu_threshold
    )


# ---------------------------------------------------------
# TEMPORAL DECAY (PERSISTENCE)
# ---------------------------------------------------------
def compute_temporal_persistence_score(
    *,
    confirming_windows: int,
    confirming_timestamps: list,
    current_timestamp: float,
    required_windows: int = 2,
    half_life_days: int = 90,
) -> float:
    """
    Computes persistence with exponential temporal decay.
    """

    if confirming_windows == 0 or not confirming_timestamps:
        return 0.0

    lambda_decay = math.log(2) / half_life_days

    weighted_sum = 0.0
    for ts in confirming_timestamps:
        delta_days = max((current_timestamp - ts) / 86400.0, 0.0)
        weighted_sum += math.exp(-lambda_decay * delta_days)

    return clamp(weighted_sum / required_windows)


# ---------------------------------------------------------
# VOLUME-WEIGHTED CONSISTENCY (EXISTING)
# ---------------------------------------------------------
def compute_volume_weighted_consistency_score(
    *,
    segment_variances: list,
    segment_sizes: list,
) -> float:
    """
    Computes consistency score weighted by segment volume.

    Small noisy segments cannot dominate global truth.
    """

    if not segment_variances or not segment_sizes:
        return 1.0

    total_size = sum(segment_sizes)
    if total_size <= 0:
        return 1.0

    weighted_variance = 0.0
    for var, size in zip(segment_variances, segment_sizes):
        weight = size / total_size
        weighted_variance += weight * clamp(var)

    return clamp(1.0 - weighted_variance)


# ---------------------------------------------------------
# REGIME-AWARE CONSISTENCY (NEW, SAFE WRAPPER)
# ---------------------------------------------------------
def compute_regime_consistency_score(
    *,
    per_regime_variances: List[float],
    per_regime_sizes: List[int],
) -> float:
    """
    Computes consistency across operating regimes.

    SAFE EXTENSION:
    - Reuses existing volume-weighted consistency
    - No new math
    - No new assumptions
    - Fail-open

    If regime data is unavailable → returns 1.0
    """

    try:
        if not per_regime_variances or not per_regime_sizes:
            return 1.0

        return compute_volume_weighted_consistency_score(
            segment_variances=per_regime_variances,
            segment_sizes=per_regime_sizes,
        )
    except Exception:
        return 1.0


# ---------------------------------------------------------
# UNIVERSAL CONFIDENCE FUNCTION (LOCKED)
# ---------------------------------------------------------
def compute_confidence(
    *,
    row_count: int,
    signal_score: float,
    temporal_persistence_score: float,
    consistency_score: float,
    penalty_score: float = 0.0,
    effect_size_factor: float = 1.0,
    ordered_data_factor: float = 1.0,
) -> float:
    """
    Computes final confidence score for any insight candidate.

    SINGLE SOURCE OF TRUTH.

    F-08: All confidence adjustments must flow through this function.
    effect_size_factor:  multiplier based on delta_pct (0.3 for tiny, 0.6 for small, 1.0 default)
    ordered_data_factor: 0.6 for unordered BIAS signals, 1.0 otherwise
    """

    # Weights (LOCKED)
    W_N = 0.25
    W_SIGNAL = 0.30
    W_PERSISTENCE = 0.20
    W_CONSISTENCY = 0.15
    W_PENALTY = 0.10

    n_score = compute_sample_size_score(row_count=row_count)

    confidence = (
        W_N * n_score
        + W_SIGNAL * clamp(signal_score)
        + W_PERSISTENCE * clamp(temporal_persistence_score)
        + W_CONSISTENCY * clamp(consistency_score)
        - W_PENALTY * clamp(penalty_score)
    )

    # F-08: Apply consolidated factors (replaces ad-hoc mutations in event_engine)
    confidence *= clamp(effect_size_factor)
    confidence *= clamp(ordered_data_factor)

    return clamp(confidence)

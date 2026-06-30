# AEGIS SYSTEM AUDIT — Decision Intelligence Correctness Review

**Auditor**: AI Systems Architect (Claude Opus 4.6)
**Date**: 2026-04-16
**Scope**: Full decision pipeline — signal detection through decision output
**Files reviewed**: 35+ core Python modules across 12 subsystems
**Audit type**: Logic correctness, failure mode analysis, decision quality

---

## 1. System Overview

AEGIS is a deterministic decision intelligence system that converts tabular data into
structured business decisions. The pipeline has seven stages:

```
CSV Upload
  → DataSanitizer + SemanticMapper + RealityReader (profiling)
  → Company Brain V2 (DominanceDetector, BiasDetector, TradeoffDetector)
  → Event Engine (role assignment, filtering, normalization)
  → Correctness Layer (direction validation, identifier rejection)
  → Decision Synthesizer (pattern matching → business decisions)
  → Decision Validator (subsampling stability) + Cross-Validator (domain rules)
  → Segment Engine + Insight Layer (WHERE attribution, balanced output)
```

**Design strengths observed**:
- Fail-open architecture throughout — no single component crash kills the pipeline
- Deterministic sort keys at every stage for reproducibility
- Layered confidence gating (CUSUM threshold → signal_score → confidence → consistency)
- Correctness layer that validates signal direction against actual data
- Belt-and-suspenders identifier filtering (column_filter + event_engine + correctness_layer)

**Design philosophy**: The system generates candidate signals, then progressively filters
them through confidence gates, correctness validation, stability checks, and cross-metric
validation before producing output. Silence is a valid output state.

---

## 2. Identified Failures

### F-01: DOMINANCE POLARITY INVERSION (CRITICAL)

**Location**: `core/event_engine.py:293-296` (`_infer_direction_from_primitive`)

**What happens**: Every DOMINANCE insight (CATEGORICAL, POINT, RANGE_STD, RANGE_QUANTILE)
is mapped to direction `"DOWNWARD"`. The comment says "dominance = declining diversity =
risk direction" — but this conflates a structural property (concentration) with a temporal
direction (decline).

**Example**: A sales dataset where 85% of revenue comes from "Enterprise" segment. The
DominanceDetector correctly identifies this as CATEGORICAL dominance. The event_engine
then labels it DOWNWARD. The decision synthesizer sees a DOWNWARD OUTPUT signal and may
produce a `DEMAND_DECLINE` decision: "Revenue is declining" — when revenue is actually
stable and concentrated.

**Why it's wrong**: Dominance is an instantaneous structural property. UPWARD/DOWNWARD
are temporal directions. Forcing dominance into a directional framework creates false
decline signals for stable concentrated metrics.

**Impact**: Any metric with legitimate concentration (common in real business data — e.g.,
80/20 revenue splits, single-region operations) will be misreported as declining. This
is the highest-impact bug in the system because concentration is extremely common.

**Root cause**: The event_engine requires all signals to have UPWARD/DOWNWARD direction
to participate in decision synthesis. Dominance has no natural direction, so a false one
was assigned to avoid dropping the signal.

---

### F-02: TRADEOFF DETECTOR CONFLATES CORRELATION WITH TRADEOFF (HIGH)

**Location**: `company_brain/tradeoff_detector.py:133-138`

**What happens**: The TradeoffDetector uses Pearson correlation between all numeric column
pairs. Any pair with |r| >= 0.3 and p < 0.2 is reported as a "TRADEOFF". But:

- A **positive** correlation between Revenue and Cost is normal co-scaling, not a tradeoff
- A **positive** correlation between Ad_Spend and Revenue is the desired business outcome
- Only **negative** correlations where one metric improving hurts another are true tradeoffs

**Example**: Revenue and COGS naturally co-move (r=0.85). The system reports:
"A structural tradeoff exists: improving Revenue is associated with increased risk in COGS."
This is not a tradeoff — it's fundamental business mechanics.

**Additional issue**: The narrative in `orchestrator_v2.py:239-243` always frames tradeoffs
as "improving X is associated with increased risk in Y" regardless of correlation sign.

**Root cause**: No economic polarity filter. The detector measures statistical association
but doesn't interpret whether the association is expected, benign, or problematic.

---

### F-03: CONFIDENCE ENGINE RECEIVES HARDCODED PERFECT SCORES (HIGH)

**Location**: `company_brain/orchestrator_v2.py:92-95`

```python
confidence = compute_confidence(
    row_count=historical_row_count,
    signal_score=candidate.get("signal_score", 0.0),
    temporal_persistence_score=1.0,   # ← ALWAYS 1.0
    consistency_score=1.0,            # ← ALWAYS 1.0
    penalty_score=0.0,                # ← ALWAYS 0.0
)
```

**What happens**: The confidence formula allocates 35% weight to temporal persistence (20%)
and consistency (15%). Both are hardcoded to maximum. This means:

- A signal seen in one data upload gets the same temporal score as one confirmed across 12 months
- A signal present in only one segment gets the same consistency as one present across all segments
- The effective confidence formula collapses to: `0.25 * N_score + 0.30 * signal_score + 0.35`

The minimum possible confidence for any signal (with adequate rows) is 0.35 + 0.25 = 0.60,
which nearly clears the 0.7 threshold just from the hardcoded terms.

**Root cause**: The persistence and consistency scoring functions exist (`compute_temporal_
persistence_score`, `compute_volume_weighted_consistency_score`) but the orchestrator never
calls them with real data. Likely deferred during development and never connected.

---

### F-04: METRIC ROLE INFERENCE IS A DEAD STUB (HIGH)

**Location**: `company_brain/metric_roles.py:22-25`

```python
def resolve_metric_roles(...) -> Dict[str, Any]:
    return {}   # ← always empty
```

**What happens**: The orchestrator calls `resolve_metric_roles()` at step 0 but gets back
an empty dict. Meanwhile, `metric_role_inference.py` contains a working behavioral role
inference engine (based on CV, range, outlier ratio) that is never called.

Downstream, `event_engine._assign_role()` falls back to name-based matching via a hardcoded
registry of ~40 metric names and keyword regexes. Any metric with a non-standard name
(e.g., "Monthly_Movements", "FTE_Count", "Throughput_Rate") gets role UNKNOWN.

**Impact**: UNKNOWN-role metrics cannot match any decision pattern (EFFICIENCY_GAIN,
DEMAND_DECLINE, etc.) and fall through to the `_unknown_pattern` fallback, which produces
generic "STRUCTURAL_CHANGE" decisions with artificially boosted confidence.

**Root cause**: The behavioral inference module was built but never wired into the pipeline.

---

### F-05: FIRST-UPLOAD BASELINE BOOTSTRAPPING IS FRAGILE (MEDIUM-HIGH)

**Location**: `api/routes.py:293-299`, `company_brain/orchestrator_v2.py:65-71`

**What happens**: On the first upload for a tenant+domain:
1. `previous_numeric_baseline` is empty (no prior baseline in DB)
2. BiasDetector is skipped entirely (`bias_baseline_stats={}` → `result = []`)
3. `current_stats` becomes both the reality snapshot AND the implicit baseline
4. This first-upload snapshot is persisted as the baseline for all future comparisons

**Problem**: If the first upload is anomalous (seasonal spike, data error, partial extract),
every future upload will be compared against a bad baseline. The system has no mechanism to:
- Detect whether the first baseline is representative
- Require minimum uploads before establishing a stable baseline
- Age out or decay old baselines

**Root cause**: No baseline quality gate. The system trusts the first upload unconditionally.

---

### F-06: REGIME_SHIFT AUTO-PROMOTION OVERRIDES SIGNAL IDENTITY (MEDIUM-HIGH)

**Location**: `core/event_engine.py:232-236`

```python
if delta_pct > 0.5:
    direction = "UPWARD" if current_mean > baseline_mean else "DOWNWARD"
    primitive = "REGIME_SHIFT"
```

**What happens**: Any signal where the current mean differs from baseline by >50% is
silently promoted to REGIME_SHIFT, regardless of its original primitive type. A DOMINANCE
insight about categorical concentration, or a TRADEOFF about metric co-movement, becomes
a REGIME_SHIFT if the effect size is large enough.

**Downstream consequence**: REGIME_SHIFT events receive special treatment:
- Forced to front of synthesis queue (`decision_pipeline.py:155`)
- Bypass consistency validation (`decision_validator.py:108`)
- Get dedicated narrative generation with hardcoded role maps (`decision_synthesizer.py:444-459`)

**Root cause**: The effect-size gate was designed for BIAS signals but applies globally
to all primitives.

---

### F-07: FALLBACK CHAIN GUARANTEES THE SYSTEM ALWAYS SPEAKS (MEDIUM)

**Location**: Multiple files — `event_engine.py:145-162`, `decision_synthesizer.py:621-719`

**What happens**: The system has three fallback layers that prevent empty output:

1. **Event Engine fallback**: If strict filtering rejects all events, relaxed mode fires
   with capped confidence (0.5)
2. **Synthesizer fallback 1**: If no named pattern matches, `_unknown_pattern` fires
3. **Synthesizer fallback 2**: If still no pattern, direct event conversion fires
4. **Synthesizer backfill**: If fewer than 3 decisions, pad with SIGNAL_CONTEXT

**Problem**: AEGIS's design philosophy says "silence is intentional and correct" (the SILENT
system state). But these fallback layers ensure the decision synthesizer almost never returns
empty. A dataset with only noise will still produce 3 decisions — just low-quality ones.

The system state can correctly be SILENT (no insight meets threshold), but the decision
pipeline runs independently and produces decisions from events that cleared the confidence
gate at 0.5, not 0.7.

**Root cause**: The confidence threshold for system state (0.7) and the event validation
threshold (0.5 in `decision_synthesizer.py:559`) are different. The decision pipeline
operates on a lower bar than the brain output.

---

### F-08: CONFIDENCE MANIPULATION OUTSIDE THE UNIVERSAL FUNCTION (MEDIUM)

**Location**: Multiple files

The confidence engine declares itself "SINGLE SOURCE OF TRUTH" but confidence is modified
in at least 5 other locations:

| Location | Modification |
|----------|-------------|
| `event_engine.py:258-265` | `confidence *= 0.3` or `*= 0.6` based on delta_pct |
| `event_engine.py:264-265` | `confidence *= 0.6` for unordered BIAS |
| `decision_synthesizer.py:357-358` | `conf += 0.10` for strong segment deviation |
| `decision_synthesizer.py:399-400` | `conf += 0.10` for strong segment deviation (again) |
| `cross_validator.py:358-361` | `conf += 0.15` or `conf -= 0.25` |
| `cross_validator.py:372-376` | `conf = 0.5` or `conf = 0.4` floor from segment deviation |

**Problem**: The final confidence number in a decision is the product of ~6 independent
adjustments, none of which know about the others. A signal can be penalized by delta_pct
in the event engine, then boosted by segment deviation in the synthesizer, then boosted
again by cross-validation — making the final number unauditable.

**Root cause**: Confidence adjustments were added incrementally at different pipeline stages
without consolidating them into the confidence engine.

---

### F-09: QUALITY_DETERIORATION HARDCODED TO HIGH PRIORITY (MEDIUM)

**Location**: `company_brain/decision_synthesizer.py:241`

```python
"priority": "HIGH",   # quality deterioration is always high priority
```

**What happens**: Any quality metric trending upward (defects, churn, etc.) gets HIGH
priority regardless of confidence or impact. A barely-significant 51% confidence quality
signal with 0.1 impact score gets HIGH, while a 95% confidence demand decline with 0.9
impact gets MEDIUM.

**Root cause**: Domain assumption baked into a "domain-agnostic" detector.

---

### F-10: CAUSAL CORE FILLS NaN WITH ZERO (MEDIUM)

**Location**: `causality/causal_core.py:145`

```python
df = df.fillna(0)
```

**What happens**: Missing values are replaced with 0 before computing lagged correlations
and transfer entropy. If Revenue is missing for Q3 (NaN → 0), this creates an artificial
spike downward that correlates with whatever other metrics changed in Q3.

**Root cause**: Simple preprocessing choice that doesn't account for the statistical
impact of zero-imputation on correlation measures.

---

### F-11: CORRECTNESS LAYER 30/70 SPLIT IS POSITION-SENSITIVE (MEDIUM)

**Location**: `core/correctness_layer.py:195-196`

```python
split = int(n * 0.3)
baseline_mean = float(series.iloc[:split].mean())
current_mean  = float(series.iloc[split:].mean())
```

**What happens**: The correctness layer validates signal direction by comparing the first
30% of rows against the last 70%. But for unordered data (no time column), row order is
arbitrary — the "baseline" is just the first 30% of whatever order the CSV was in.

The code handles this at line 187-189 (sets change to 0 for unordered data), but this
means the correctness layer provides NO directional validation for unordered datasets.
Signals pass through unvalidated with only the "FLAT" gate active.

**Root cause**: The correctness layer's temporal split design doesn't degrade gracefully
for non-temporal data.

---

### F-12: XGBoost AND SHAP MODULES VIOLATE "NO ML" CONSTRAINT (LOW-MEDIUM)

**Location**: `company_brain/xgboost_engine.py`, `company_brain/shap_validator.py`

**What happens**: These modules train XGBoost models and compute SHAP values. They are
fail-open (imported with try/except), but they exist in the codebase and are called from
the impact analysis pathway.

**Tension**: The system's stated design principle is deterministic, no-ML decision making.
XGBoost is a stochastic ML model (subsample=0.8, colsample_bytree=0.8 introduce randomness).

**Root cause**: These were likely added for impact attribution before the "no ML" constraint
was formalized. They remain because they're fail-open and don't block the core pipeline.

---

### F-13: SEGMENT DEVIATION THRESHOLD INCONSISTENCY (LOW-MEDIUM)

**Location**: `core/segment_engine.py:44` vs `core/segment_engine.py:301`

| Function | Threshold | Purpose |
|----------|-----------|---------|
| `enrich_signals_with_segments` | 20% deviation | Attach WHERE context to signals |
| `generate_segment_decisions` | 5% deviation | Generate segment-level decisions |

**What happens**: A segment with 15% deviation will appear in segment decisions but NOT
be attached to the signal it explains. The insight layer (which reads segment context from
signals) will miss it, while the segment decisions (which are displayed separately) will
show it. This creates inconsistent attribution between different parts of the response.

---

## 3. Root Cause Analysis (Systemic)

The individual failures above trace to five systemic root causes:

### RC-1: Direction-First Architecture
The entire pipeline assumes every signal has a direction (UPWARD/DOWNWARD). This works for
BIAS (drift) but not for DOMINANCE (concentration) or TRADEOFF (correlation). Forcing
non-directional primitives into a directional schema causes polarity errors (F-01, F-02).

### RC-2: Disconnected Confidence Model
The confidence engine was designed as a multi-factor score (sample size, signal strength,
temporal persistence, consistency, penalties) but only two factors are connected. The
remaining factors are hardcoded to neutral/max, making confidence overoptimistic (F-03).
Additional ad-hoc adjustments at other pipeline stages compound the problem (F-08).

### RC-3: Name-Based Rather Than Behavior-Based Semantics
Metric roles are assigned by name pattern matching rather than statistical behavior. A
behavioral role inference engine exists but isn't connected (F-04). This causes role
misassignment for any metric with non-standard naming.

### RC-4: Missing Baseline Lifecycle
The system has no concept of baseline maturity. The first upload becomes truth, regardless
of quality (F-05). There is no baseline aging, multi-upload averaging, or minimum history
requirement before the system trusts its own baselines.

### RC-5: Aggressive Anti-Silence Fallbacks
The fallback chain (F-07) works against the system's own silence principle. The brain can
correctly determine SILENT, but the decision pipeline independently produces decisions at
a lower confidence bar, creating contradictory output.

---

## 4. Priority of Fixes

### CRITICAL (Must fix — produces wrong decisions)

| ID | Issue | Impact |
|----|-------|--------|
| F-01 | Dominance polarity inversion | False decline signals for concentrated metrics |

### HIGH (Should fix — degrades decision quality significantly)

| ID | Issue | Impact |
|----|-------|--------|
| F-02 | Tradeoff conflates correlation with tradeoff | Natural co-movements reported as risks |
| F-03 | Confidence hardcoded to 1.0 for persistence/consistency | All signals artificially overconfident |
| F-04 | Metric role inference is a dead stub | Non-standard metrics get UNKNOWN role and weak decisions |

### MEDIUM-HIGH (Should fix — creates silent failures)

| ID | Issue | Impact |
|----|-------|--------|
| F-05 | First-upload baseline fragility | Bad first upload poisons all future comparisons |
| F-06 | REGIME_SHIFT auto-promotion | Dominance/tradeoff signals hijacked into regime shifts |

### MEDIUM (Should fix — reduces reliability)

| ID | Issue | Impact |
|----|-------|--------|
| F-07 | Fallback chain prevents silence | System speaks when it shouldn't |
| F-08 | Confidence manipulation outside engine | Final confidence is unauditable |
| F-09 | Quality always HIGH priority | Priority ranking is distorted |
| F-10 | NaN→0 in causal core | False correlations from imputed zeros |
| F-11 | Correctness layer ineffective for unordered data | No direction validation without timestamps |

### LOW-MEDIUM (Should address — design inconsistencies)

| ID | Issue | Impact |
|----|-------|--------|
| F-12 | XGBoost/SHAP violate no-ML principle | Design tension, non-deterministic |
| F-13 | Segment threshold mismatch | Inconsistent segment attribution |

---

## 5. Suggested Improvements (Logic-Level)

### IMP-01: Fix Dominance Polarity — Create NON-DIRECTIONAL Primitive Path (CRITICAL)

**Problem it fixes**: F-01 — false decline signals from concentration

**Logic rule**: Dominance signals should NOT flow through the UPWARD/DOWNWARD pathway.
They are structural properties, not temporal directions.

**Approach**:

1. In `event_engine._infer_direction_from_primitive()`: Return a new direction `"STRUCTURAL"`
   instead of `"DOWNWARD"` for dominance subtypes.

2. In `event_engine._convert_insight()`: Allow `"STRUCTURAL"` as a valid direction that
   bypasses the directional gates.

3. In `decision_synthesizer.synthesize_decisions()`: Add a dedicated handler for
   STRUCTURAL-direction events BEFORE role-based grouping. Dominance events produce
   `"CONCENTRATION_RISK"` decisions directly, not via the INPUT/OUTPUT/VALUE role groups.

4. In the narrative generator: Add a CONCENTRATION_RISK sentence template that describes
   the concentration factually without claiming a direction.

**Key constraint**: This must not break existing BIAS or TRADEOFF flows. Only DOMINANCE
primitives get the new path.

---

### IMP-02: Add Economic Polarity Filter to TradeoffDetector (HIGH)

**Problem it fixes**: F-02 — natural co-movements reported as tradeoffs

**Logic rule**: A tradeoff exists only when improving one metric structurally harms another.
Positive correlation between two metrics of the SAME economic direction (both good or both
bad) is co-movement, not a tradeoff.

**Approach**:

1. After computing Pearson correlation, classify the pair using the role registry:
   - Same-direction pair (e.g., Revenue + Profit, both "good-up"): positive correlation
     is EXPECTED, negative is a CONFLICT
   - Opposite-direction pair (e.g., Revenue + Cost, one "good-up" one "good-down"):
     negative correlation is EXPECTED, positive is a TRADEOFF

2. Add a `polarity` field to each tradeoff result: `"TRUE_TRADEOFF"` | `"CONFLICT"` |
   `"CO_MOVEMENT"`.

3. Only emit `"TRUE_TRADEOFF"` and `"CONFLICT"` as candidates. Filter out `"CO_MOVEMENT"`.

**Minimal implementation**: Add a `_classify_pair_polarity(role_a, role_b, correlation_sign)`
function to `tradeoff_detector.py`. Define a 7x7 role-pair matrix:

```
            INPUT  OUTPUT  VALUE  COST  QUALITY  TRANSFER  UNKNOWN
INPUT       CO     CO      CO     CO    INVERSE  NEUTRAL   UNKNOWN
OUTPUT      CO     CO      CO     INV   INVERSE  NEUTRAL   UNKNOWN
VALUE       CO     CO      CO     INV   INVERSE  NEUTRAL   UNKNOWN
COST        CO     INV     INV    CO    CO       NEUTRAL   UNKNOWN
QUALITY     INV    INV     INV    CO    CO       NEUTRAL   UNKNOWN
TRANSFER    NEU    NEU     NEU    NEU   NEU      CO        UNKNOWN
UNKNOWN     UNK    UNK     UNK    UNK   UNK      UNK       UNKNOWN
```

Where CO=co-movement expected, INV=inverse expected, NEU=no expectation.

---

### IMP-03: Connect Temporal Persistence and Consistency Scoring (HIGH)

**Problem it fixes**: F-03 — all signals artificially overconfident

**Logic rule**: Confidence should reflect how often a signal has been confirmed across
multiple data uploads (persistence) and how consistently it appears across data segments
(consistency).

**Approach**:

1. **Persistence**: Use the EventStore's historical data. For each candidate insight,
   query the event store for the same tenant+domain+metric. Count how many prior time
   windows confirmed the same directional signal. Pass this count to
   `compute_temporal_persistence_score()`.

2. **Consistency**: Use the segment engine's pre-computed segment deviations. For each
   candidate insight, check whether the signal direction is consistent across the top
   segments. Compute variance of segment-level means. Pass to
   `compute_volume_weighted_consistency_score()`.

3. **In orchestrator_v2.py**: Replace the hardcoded `1.0` values with actual computed
   scores. If historical data or segment data is unavailable, use a conservative default
   of `0.5` (neutral), not `1.0` (perfect).

---

### IMP-04: Wire Behavioral Metric Role Inference (HIGH)

**Problem it fixes**: F-04 — non-standard metrics get UNKNOWN role

**Logic rule**: When name-based role assignment returns UNKNOWN, fall back to behavioral
inference from the metric's statistical signature.

**Approach**:

1. In `event_engine._assign_role()`: After the keyword fallback returns UNKNOWN, call
   `infer_metric_roles()` from `metric_role_inference.py` using the metric's stats from
   the reality snapshot.

2. Map the inferred behavioral scores to roles using the highest-scoring role:
   - `efficiency` → VALUE
   - `risk` → QUALITY
   - `outcome` → OUTPUT
   - `cost_driver` → INPUT

3. Require a minimum score threshold (e.g., 0.4) to assign a role. Below that, keep
   UNKNOWN — it's better to be unknown than wrongly classified.

---

### IMP-05: Add Baseline Maturity Gate (MEDIUM-HIGH)

**Problem it fixes**: F-05 — bad first upload poisons baseline

**Logic rule**: A baseline should not be trusted until confirmed by multiple uploads.

**Approach**:

1. Add a `upload_count` field to the baseline persistence layer. Increment on each upload.

2. Define maturity levels:
   - `upload_count < 2`: IMMATURE — use baseline but flag all comparisons as preliminary
   - `upload_count >= 2 and < 5`: DEVELOPING — use baseline, apply a confidence penalty (0.8x)
   - `upload_count >= 5`: MATURE — full confidence

3. Pass the maturity level to the confidence engine as a baseline reliability multiplier.

---

### IMP-06: Scope REGIME_SHIFT Promotion to BIAS Only (MEDIUM-HIGH)

**Problem it fixes**: F-06 — dominance/tradeoff signals hijacked

**Logic rule**: REGIME_SHIFT promotion should only apply to signals that are directional
by nature (BIAS). Dominance and tradeoff signals should never be promoted.

**Approach**: In `event_engine._convert_insight()`, add a guard:

```python
if delta_pct > 0.5 and primitive == "BIAS":
    primitive = "REGIME_SHIFT"
```

This is a one-line change with no side effects.

---

### IMP-07: Align Decision Pipeline Confidence Floor with System State (MEDIUM)

**Problem it fixes**: F-07 — system speaks when brain says silence

**Logic rule**: The decision pipeline should not produce decisions when the system state
is SILENT.

**Approach**: In `routes.py`, after computing `brain_output`, check the system state. If
SILENT or OBSERVATION, skip the decision pipeline entirely (or pass the state to
`run_decision_pipeline` and let it early-return).

---

### IMP-08: Consolidate Confidence Adjustments Into the Engine (MEDIUM)

**Problem it fixes**: F-08 — confidence is adjusted at 6 different locations

**Logic rule**: All confidence adjustments should be inputs to `compute_confidence()`,
not post-hoc multipliers.

**Approach**:

1. Add parameters to `compute_confidence()`:
   - `effect_size_factor: float` (replaces event_engine delta_pct penalty)
   - `ordered_data_factor: float` (replaces unordered BIAS penalty)
   - `segment_agreement_factor: float` (replaces cross-validator boost)

2. Remove all post-hoc `confidence *= X` and `confidence += X` from event_engine,
   decision_synthesizer, and cross_validator.

3. Each stage computes its factor and passes it forward; the confidence engine combines
   them in one formula.

---

### IMP-09: Compute Quality Priority From Confidence x Impact (MEDIUM)

**Problem it fixes**: F-09 — quality always HIGH

**Logic rule**: Quality signals should use the same priority function as everything else.

**Approach**: In `_quality_deterioration()`, replace `"priority": "HIGH"` with
`"priority": _priority(conf, imp)`. Add a quality amplifier inside `_priority()` that
gives quality a 1.5x multiplier on the score, rather than bypassing the function entirely.

---

### IMP-10: Use Pairwise Deletion Instead of Zero Fill (MEDIUM)

**Problem it fixes**: F-10 — false correlations from NaN→0

**Logic rule**: Missing values should be excluded from correlation computation, not
replaced with artificial values.

**Approach**: In `causal_core.py._prepare()`, replace `df.fillna(0)` with `df.dropna()`.
For transfer entropy, use pairwise complete observations: drop rows where either the
source or target column is NaN before computing the score.

---

## 6. Edge-Case Validation Scenarios

### Scenario 1: Concentrated But Stable Business

**Data**: 5,000 rows. Revenue has 82% from "Enterprise", 18% from "SMB". Revenue mean
is stable (baseline mean = current mean ±1%).

**Expected behavior**: DOMINANCE detected. System should describe concentration factually.
No DEMAND_DECLINE. Confidence should NOT be inflated.

**Current behavior (F-01)**: DOMINANCE → DOWNWARD → Revenue declining → DEMAND_DECLINE
decision. **Wrong.**

---

### Scenario 2: Naturally Co-Moving Metrics

**Data**: 10,000 rows with Revenue and COGS. Correlation r=0.92 (p<0.001). Both trending
upward 15% vs baseline.

**Expected behavior**: This is normal co-scaling. No tradeoff. Possibly a GROWTH_SIGNAL.

**Current behavior (F-02)**: TradeoffDetector fires (r=0.92 > 0.3). Reports TRADEOFF
between Revenue and COGS. Narrative says "improving Revenue is associated with increased
risk in COGS." **Misleading.**

---

### Scenario 3: First Upload Is Anomalous

**Data**: First upload has 2,000 rows from December (holiday spike). Revenue mean = $500.
Second upload has 2,000 rows from January (normal). Revenue mean = $300.

**Expected behavior**: System should be cautious about declaring a 40% decline. The
baseline is immature.

**Current behavior (F-05)**: December baseline ($500) is trusted fully. January shows
-40% delta. Strong BIAS DOWNWARD signal, possibly promoted to REGIME_SHIFT (F-06).
System produces HIGH priority DEMAND_DECLINE. **Overreaction to seasonal noise.**

---

### Scenario 4: Non-Standard Metric Names

**Data**: 3,000 rows with columns: "FTE_Count", "Throughput_Rate", "Cycle_Time",
"Yield_Pct". No column matches the canonical role registry or keyword patterns.

**Expected behavior**: System should infer roles from statistical behavior and produce
meaningful decisions about the relationships between these metrics.

**Current behavior (F-04)**: All four get role UNKNOWN. They cannot match any named
pattern (EFFICIENCY_GAIN, etc.). Fallback `_unknown_pattern` fires with generic
"STRUCTURAL_CHANGE" decisions. **Uninformative.**

---

### Scenario 5: Conflicting Signals Across Segments

**Data**: 8,000 rows. Revenue UPWARD globally (+12%). But in segment "EMEA" (-15%) and
segment "APAC" (+45%). EMEA has 60% of rows, APAC has 20%.

**Expected behavior**: The system should flag that the global upward trend is misleading —
it's driven entirely by APAC while the majority segment (EMEA) is declining. This is a
Simpson's Paradox scenario.

**Current behavior**: The global signal passes correctness (change > 1%). Segment engine
attaches EMEA and APAC as context. But no specific detector identifies that the majority
segment contradicts the global direction. The consistency score would catch this — if it
weren't hardcoded to 1.0 (F-03). **Missed insight.**

---

### Scenario 6: Sparse Quality Metric With Legitimate Signal

**Data**: 5,000 rows. Defect_Rate is 0 for 55% of rows (legitimate — most batches have
zero defects). But non-zero defects are trending upward.

**Expected behavior**: Quality signal should be detected despite high zero ratio.

**Current behavior**: `event_engine.py:216` rejects signals with `zero_ratio > 0.50`.
Defect_Rate (55% zeros) is rejected. The quality deterioration pattern never fires.
**False negative for sparse-but-real quality signals.**

---

### Scenario 7: Decision Pipeline Produces Decisions But Brain Says SILENT

**Data**: 3,000 rows. Weak signals exist (signal_score 0.2-0.3). No insight clears the
0.7 confidence threshold in the brain.

**Expected behavior**: System state is SILENT. No decisions should be produced.

**Current behavior (F-07)**: Brain correctly returns SILENT. But the decision pipeline
runs independently on events that cleared the 0.5 threshold. The fallback chain produces
3 decisions. The API response contains `system_state: "SILENT"` alongside 3 decisions.
**Contradictory output.**

---

## 7. Summary

AEGIS has a strong architectural foundation: layered validation, fail-open design,
deterministic processing, and a clear separation between signal detection and decision
synthesis. The system's instinct to "stay silent when uncertain" is correct and valuable.

The critical issues are concentrated in three areas:

1. **Polarity handling** (F-01, F-02): The system forces all signals into a directional
   framework that doesn't fit structural properties like concentration and co-movement.

2. **Confidence integrity** (F-03, F-08): The confidence score — the system's primary
   decision gate — is inflated by hardcoded inputs and fragmented by ad-hoc adjustments.

3. **Role assignment** (F-04): The behavioral role inference engine exists but isn't
   connected, causing most real-world metrics to fall through to generic fallbacks.

Fixing these three areas would eliminate the majority of wrong decisions the system can
produce, without adding complexity or changing the architecture.

---

*End of audit.*

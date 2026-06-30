# AEGIS — Full Technical Specification

> A deterministic, multi-tenant **decision intelligence kernel** that ingests
> tabular business data and emits ranked, auditable business decisions
> through a chain of statistical detectors, a layered confidence engine, a
> correctness validator, and a fail-open synthesis pipeline.
>
> This document is the **end-to-end** technical reference: every module,
> every gate, every formula. It is written so a CTO can read it linearly,
> understand the *why* behind every layer, and reason about its failure
> modes without opening the codebase.

---

## 0. Executive Summary

AEGIS is not an LLM, not an ML platform, and not a BI dashboard. It is a
**rule-driven epistemic engine** built around three contracts:

1. **MIU (Minimum Information Unit) gate** — the system refuses to speak
   below ~1,000 rows. Below that, system state is `OBSERVATION`.
2. **Silence is a valid output** — if no signal clears the confidence
   threshold, the system returns `SILENT` rather than fabricate insight.
3. **Determinism** — same CSV in, same JSON out. Sorted keys at every
   stage, no randomness in the core decision path, no model temperature.

The pipeline transforms a raw CSV into structured decisions via the chain:

```
CSV
 → DatasetProfiler         (column typing, role hints)
 → DataSanitizer            (currency / % / NaN normalization)
 → SemanticMapper           (column-name → canonical schema)
 → RealityReader            (per-column statistics)
 → QualityGate              (row-level admissibility)
 → BaselinePersistence      (Postgres / SQLite snapshot)
 → DriftDetector            (σ-band comparison vs last baseline)
 → CompanyBrain V2:
       DominanceDetector    (concentration primitives)
       BiasDetector         (√N-scaled CUSUM drift)
       TradeoffDetector     (Pearson + economic-polarity filter)
 → ConfidenceEngine         (5-factor weighted score)
 → SystemState              (OBSERVATION / SILENT / INSIGHTFUL)
 → EventEngine              (normalize → strict event schema)
 → CorrectnessLayer         (direction validation; 30/70 split)
 → DecisionSynthesizer      (pattern-match → business decisions)
 → DecisionValidator        (subsampling stability)
 → CrossValidator           (domain consistency)
 → SegmentEngine            (WHERE attribution)
 → InsightLayer             (TRADEOFF / RISK / OPPORTUNITY)
 → RelativeIntelligence     (segment vs global)
 → DecisionCompressor       (rank + dedup → top-5)
 → Narration + Chatbot      (deterministic natural-language wrap)
```

Each stage is **fail-open**: a single-component crash never kills the
request; the stage is skipped, a warning is logged, and the pipeline
continues with a degraded but valid response.

---

## 1. System Architecture

### 1.1 Repository Layout

```
aegis_ai/
├── api/                  FastAPI entrypoint (routes.py, main.py)
├── sanitizer/            data_sanitizer, semantic_mapper, column_filter, quality_gate
├── brains/               reality_reader, drift_detector, baseline learners, planner, risk
├── company_brain/        V2 orchestrator + detectors + confidence + synthesizer
├── core/                 event_engine, correctness_layer, decision_pipeline,
│                         decision_validator, cross_validator, segment_engine,
│                         insight_layer, relative_intelligence, narration, chatbot,
│                         structured_output
├── causality/            TimeCausalGraph (lagged correlation), TransferEntropyEngine,
│                         pc_algorithm
├── spine/                event_store (SQLite WAL), normalizer, ingestion_router,
│                         lineage_audit
├── agents/               canonical (regime, heartbeat, escalation),
│                         cognitive (consensus_resolver, planner, root_cause)
├── patterns/             isolation_forest, TCN, context_tcn, signals, consensus
├── physics/              domain physics brains (sales/ops/hr/finance/logistics)
├── memory/               pg_memory, semantic_memory_store, shadow_baseline_store,
│                         regime_stability_buffer
├── persistence/          snapshot_repository, cognitive_snapshot_repository
├── security/             api_key_manager, tenant_middleware, rate_limiter,
│                         quota_registry, redis_rate_gate, tenant_vault
├── quarantine/           drift_guard, schema_contracts, promotion_router
├── db/                   SQLAlchemy session + baseline persistence
├── llm/                  ollama_provider (optional narration only)
├── connectors/           CSV / accounting / sales / HR / logistics adapters
├── domains/              finance + manufacturing adapter rules
├── motor/                self_healing_executor (action attempts)
└── _experimental_stability/ homeostasis, immune, audit, guardrail, self-repair
```

### 1.2 Process & Tenancy Model

* **Multi-tenant** — every request is scoped by `X-API-Key` →
  `tenant_id` via `security/tenant_middleware.py`. All persistence
  (baselines, semantic mappings, event store, decision log) is keyed by
  `(tenant_id, domain)`.
* **Rate-limited** — `security/rate_limiter.py` + `redis_rate_gate.py`
  enforce per-key quotas defined in `quota_registry.py`.
* **Stateless API layer** — FastAPI workers carry no in-process state;
  baselines live in Postgres, events in SQLite (WAL), regime windows in
  the same SQLite file. Multiple workers may run safely behind a load
  balancer.
* **Hard upload guard** — `routes.py:413` rejects payloads > 500 MB to
  protect long-running workers from OOM.

### 1.3 Data Stores

| Store                  | Engine               | Purpose                                                              |
|------------------------|----------------------|----------------------------------------------------------------------|
| `aegis.db`             | Postgres (or SQLite) | tenants, semantic mappings, reality baselines, drift events           |
| `aegis_events.db`      | SQLite WAL           | high-frequency event log, monitoring windows, regime classification   |
| `aegis_memory.db`      | SQLite               | cognitive snapshots, insight ledger                                    |
| `baseline_models/`     | Pickle / Parquet     | Prophet, isolation-forest, TCN model artefacts                         |
| `tenant_universes/`    | JSON                 | per-tenant role registries and domain extensions                       |

WAL on SQLite (`PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`)
is set in `spine/event_store.py:30` to allow concurrent reads while
writes serialize through a `threading.Lock`.

---

## 2. Ingestion & Pre-Decision Layers

### 2.1 DatasetProfiler — [`core/dataset_profiler.py`]

Runs **first**, on the raw DataFrame, and tells every downstream
component what is safe to analyse.

Produces a `DatasetProfile` with:

* `time_column`, `year_column`, `month_column`, `temporal_columns`
* `valid_metrics` — numeric columns admissible for analysis
* `dimensions`   — categorical slicers (Country, Channel, ...)
* `ignored_columns` — IDs, free text, near-empty columns
* `column_profiles[]` — per-column stats: dtype, unique ratio,
  null ratio, monotonicity, value-range, sample values
* `warnings[]`

The profiler runs **before** `DataSanitizer` so it sees raw types and
can detect coercible numerics, mixed dtypes, and date-formatted strings.
Output is then translated by `_translate_profile_names()` after
SemanticMapper renames columns, so downstream stages see consistent
identifiers.

### 2.2 DataSanitizer — [`sanitizer/data_sanitizer.py`]

Per-column rule-based normalization. No ML.

Logic:

1. If column name contains `date` → `pd.to_datetime(errors="coerce")`.
2. If hinted as ID (`id|customer|transaction|order|invoice`) → cast `str`.
3. If hinted categorical (`gender|category|product|region|...`) → cast `str`.
4. Otherwise attempt numeric coercion via:
   - Strip currency symbols `[$₹€£]` and thousands separators.
   - `"15%"` → `0.15` (divides by 100).
   - `float()` else `np.nan`.

Outcome: a DataFrame where numeric columns are statistically usable and
categorical columns are not silently coerced.

### 2.3 SemanticMapper — [`sanitizer/semantic_mapper.py`]

Renames raw column headers to **canonical schema fields** so downstream
modules can rely on stable names regardless of how the customer named
their CSV columns.

Algorithm (deterministic):

1. **Exact-match registry**: a 200+ entry dictionary
   (`CANONICAL_FIELDS`) maps synonyms → canonical names
   (e.g. `["sales","turnover","gross sales","sales_amount"]` →
   `"Revenue"`).
2. **Cached learned mapping**: if a tenant has previously mapped column
   `foo_sales` → `Revenue`, the `SemanticMapping` table returns the
   cached resolution.
3. **LLM-assisted fallback** (optional, only if an Ollama provider is
   configured) — last-resort name resolution; otherwise the column
   keeps its original name.
4. **Collision guard** — `deduplicate_semantic_mappings()` ensures no
   two source columns map to the same canonical name. Collisions get
   suffixes: `Revenue`, `Revenue_2`, `Revenue_3`. Roles for suffixed
   columns are resolved by stripping the suffix.

### 2.4 RealityReader — [`brains/reality_reader.py`]

Computes the per-column statistical fingerprint used by every detector:

For each numeric column:
* `n`, `null_ratio`, `zero_ratio`, `unique_ratio`
* `mean μ`, `median`, `std σ`, `min`, `max`
* `three_sigma_outliers` — count of values where `|x − μ| > 3σ`
* `cv = σ / |μ|` — coefficient of variation
* `metabolic consistency` — flags columns where `null_ratio + zero_ratio > 0.9`

For each categorical column it captures top-K frequencies and class
counts (used by DominanceDetector and SegmentEngine).

It also computes **operating regime** signals (volume_ratio,
variance_ratio, outlier_ratio) consumed by `RegimeSegmenter`
(§4.5).

### 2.5 QualityGate — [`sanitizer/quality_gate.py`]

Row-level admissibility:
* rejects rows with > 50% null cells,
* rejects pure-NaN columns,
* surfaces `data_quality_score ∈ [0,1]` used to attenuate downstream
  confidence when the dataset is partially degraded.

### 2.6 Baseline Persistence — [`db/baselines/persistence.py`]

Per `(tenant, domain, category, column)`:
```
ReALITY_BASELINE(
  mean, median, std, min, max,
  null_ratio, zero_ratio,
  upload_date, upload_count
)
```

On upload N:
1. Load last baseline.
2. Compute drift against it (§2.7).
3. Append new snapshot.
4. Increment `upload_count`.

> **Known fragility (F-05)** — the first upload becomes the de facto
> baseline regardless of quality. A baseline-maturity gate
> (`upload_count < 5` → penalty multiplier 0.8x) is recommended; not
> yet wired.

### 2.7 DriftDetector — [`brains/drift_detector.py`]

Compares current upload statistics vs the most recent stored baseline:

```
mean_diff      = |μ_curr − μ_base|
allowed_band   = k · σ_base                  (k = sigma_threshold, default 2.0)
drift_score    = mean_diff / (allowed_band + ε)
```

Classification:
* `σ_base == 0`                 → `zero_variance_baseline` (alert)
* `mean_diff > allowed_band`    → `scale_shift` (alert)
* `null_ratio_curr > 1.5 · null_ratio_base` → `missing_shift` (alert)
* otherwise                     → `stable`

Drift events are persisted in `drift_history` for tenant-level audit.

---

## 3. The Company Brain V2 — Behavioral Primitive Detection

The brain emits **candidate insights** (primitives). It does not
generate decisions. Its three detectors run in parallel, each emitting
0-N candidates which are then fed into the confidence engine.

### 3.1 DominanceDetector — [`company_brain/dominance_detector.py`]

Detects **structural concentration** along three subtypes:

**a) Categorical dominance.** For object / low-cardinality columns:

* Compute normalized value counts `p_i = count_i / N`.
* If `p_max ≥ θ_cat` (default `θ_cat = 0.60`), emit:

```
signal_score = clamp( (p_max − θ_cat) / (1 − θ_cat), 0, 1 )
```

**b) Numeric point dominance.** Round each value to 3 decimals, then
treat as categorical. Catches discrete repetition (e.g. a "Status_Code"
column where 70% of rows equal `0.000`).

**c) Numeric range dominance.** For continuous metrics:

1. STD band (primary): `[μ − k·σ , μ + k·σ]` with `k = 0.5`. If the
   fraction of values inside the band ≥ 0.70, emit `RANGE_STD`.
2. Quantile band (fallback): `[Q25, Q75]`. Same threshold.

**Noise-floor guard** (R5/W6): if `cv = σ/|μ| < 10⁻³`, the column is
effectively constant — emission is suppressed because a "stuck sensor"
is a data bug, not an insight.

Output schema:

```
{
  "primitive": "DOMINANCE",
  "subtype":   "CATEGORICAL" | "POINT" | "RANGE_STD" | "RANGE_QUANTILE",
  "metric":    str,
  "signal_score": float ∈ [0,1],
  "evidence":  {coverage, band/dominant_value, μ, σ}
}
```

> **F-01 polarity fix** — Dominance signals are non-temporal. The event
> engine maps them to `direction = "STRUCTURAL"` and the synthesizer
> routes them to `CONCENTRATION_RISK` decisions, never to
> `DEMAND_DECLINE`.

### 3.2 BiasDetector — [`company_brain/bias_detector.py`]

Detects **persistent directional drift** using a √N-scaled CUSUM
(Cumulative Sum) test.

For each numeric metric with baseline `(μ, σ)` and current series
`x_1, …, x_n`:

```
k = 0.5 · σ                          (slack)
S⁺_t = max(0, S⁺_{t−1} + (x_t − μ − k))
S⁻_t = max(0, S⁻_{t−1} − (x_t − μ + k))
max_cusum = max_t( S⁺_t, S⁻_t )
```

The classical CUSUM threshold is `h = 3σ` calibrated against ~50
observations. For long series the cumulative sum performs a random
walk, so the threshold is **√N-scaled**:

```
σ_eff = min( 3 · √(N / 50) , 12 )
h     = σ_eff · σ
```

A signal fires only when `max_cusum > h`.

Direction: `UPWARD` if `S⁺_max > S⁻_max` else `DOWNWARD`.

Signal score (auditable ratio):

```
signal_score = clamp( (max_cusum − h) / max(h, 10⁻⁹) , 0, 1 )
```

A 30/70 split mean is also recorded for the correctness layer:

```
split            = ⌊0.3 · N⌋
μ_baseline_slice = mean(x[:split])
μ_current_slice  = mean(x[split:])
mean_shift       = | μ_current − μ_baseline |
snr_ratio        = mean_shift / σ
```

This SNR ratio acts as a downstream sanity gate without modifying the
confidence score (the universal confidence engine is the single source
of truth).

### 3.3 TradeoffDetector — [`company_brain/tradeoff_detector.py`]

For every pair of numeric metrics `(A, B)` with `≥ 50` paired non-null
rows, compute Pearson correlation:

```
r, p = scipy.stats.pearsonr(A, B)
```

A pair is admitted only if `|r| ≥ 0.30` and `p ≤ 0.20`.

**Economic-polarity filter (F-02 fix).** Every metric is assigned a
**polarity** by name regex:

* `GOOD_UP` — Revenue, Conversions, ROI, NPS, ...
* `GOOD_DOWN` — Cost, Defects, Churn, ...
* `NEUTRAL` — Inventory, Headcount, ...
* `UNKNOWN` — anything else

The pair classification matrix:

| Polarity A | Polarity B | sign(r) | Class           | Emit? |
|------------|------------|---------|------------------|-------|
| same       | same       | +       | `CO_MOVEMENT`    | no    |
| same       | same       | −       | `CONFLICT`       | yes   |
| opposite   | opposite   | −       | `EXPECTED`       | no    |
| opposite   | opposite   | +       | `TRUE_TRADEOFF`  | yes   |
| any NEUTRAL / UNKNOWN | … | … | `UNKNOWN`        | yes   |

Plus a high-correlation co-movement guard: if `pair_class == UNKNOWN`
and `r > 0.70`, the pair is dropped (two metrics moving in lock-step
positively are almost always co-scaling, not a tradeoff).

After filtering, tradeoffs are ranked by `|r|`, capped at 10, and an
adaptive floor of `0.35` is applied when the strongest signal exceeds
`0.4`.

### 3.4 Causality Layer — [`causality/`]

Separate from the brain; produces causal context attached to
decisions.

**Time-lagged correlation graph** (`causal_core.py`):
For lag `L = 1`:
```
src_lag(t)        = x_src(t − L)
tgt_current(t)    = x_tgt(t)
score(src→tgt)    = |corr(src_lag, tgt_current)|
```
Edges below `min_score = 0.05` are pruned. Each node's
`influence_score = mean(outgoing edges)`. Top-3 drivers are exported.

**Transfer entropy approximation** (`causal_core.py:160`):
Lagged mutual information using histogram-based density estimation:
```
MI(X_lag, Y_curr) = ΣΣ p(x,y) · log( p(x,y) / (p(x) p(y)) )
TE_score          = MI / (1 + MI)              (normalised to [0,1])
```
Discretization uses 10 equal-width bins; standardisation is
`(x − μ) / (σ + 10⁻⁹)`; missing values are **pairwise-deleted**
(F-10 fix; previously `fillna(0)` was creating phantom downward
spikes).

**PC algorithm stub** (`pc_algorithm.py`) — adjacency from conditional
independence tests; currently used as advisory context only.

---

## 4. Confidence, State, and Event Normalization

### 4.1 ConfidenceEngine — [`company_brain/confidence_engine.py`]

The **single source of truth** for confidence. All ad-hoc multipliers
are being migrated into this function (F-08).

The universal formula:

```
confidence =  W_N            · N_score
            + W_SIGNAL       · signal_score
            + W_PERSISTENCE  · temporal_persistence_score
            + W_CONSISTENCY  · consistency_score
            − W_PENALTY      · penalty_score

confidence ← confidence · effect_size_factor · ordered_data_factor
```

Locked weights:

| Term          | Weight |
|----------------|--------|
| `W_N`          | 0.25   |
| `W_SIGNAL`     | 0.30   |
| `W_PERSISTENCE`| 0.20   |
| `W_CONSISTENCY`| 0.15   |
| `W_PENALTY`    | 0.10   |

**Sample-size score (MIU-aware):**

```
N_score =  0                                       if N < 1000
        =  log₁₀(N / 1000) / log₁₀(10000 / 1000)   if 1000 ≤ N < 10000
        =  1                                       if N ≥ 10000
```

The denominator equals 1, so this simplifies to
`log₁₀(N/1000)` over the ramp range.

**Temporal persistence:** confirms a signal across multiple uploads
using exponential decay with half-life `T_½ = 90 days`:

```
λ = ln 2 / T_½
persistence_score = clamp( Σ_i exp(−λ · Δt_i) / required_windows )
```

`Δt_i` is days between the i-th confirming snapshot and now;
`required_windows = 2` by default.

**Volume-weighted consistency:** for K segments with per-segment
variance `v_k` and size `n_k`:

```
w_k = n_k / Σ_j n_j
consistency_score = clamp( 1 − Σ_k w_k · clamp(v_k) )
```

(Same function is reused for regime consistency; if regime data is
unavailable it returns 1.0 — fail-open.)

**Operating thresholds:**

* Hard silence floor: `N_score = 0` if `N < 1000`.
* INSIGHTFUL threshold (synthesizer-facing): `confidence ≥ 0.70`.
* SystemState threshold (`resolve_system_state`): `confidence ≥ 0.50`.

> The current orchestrator passes
> `temporal_persistence_score = consistency_score = 0.7` (neutral-positive)
> when no historical data exists, instead of the previous `1.0`
> (F-03 partial fix). 0.5 was rejected because it created an
> unreachable INSIGHTFUL ceiling of 0.725.

### 4.2 SystemState — [`company_brain/system_state.py`]

Resolves the epistemic state of the engine:

```
if row_count < MIU(=1000):              return OBSERVATION
if no insight ≥ confidence_threshold:    return SILENT
if regime_history and only one regime:   return SILENT
                                         return INSIGHTFUL
```

This is the **only** legitimate place that decides whether AEGIS is
allowed to speak. The decision pipeline should align with this state
(F-07).

### 4.3 EventEngine — [`core/event_engine.py`]

Converts heterogeneous brain primitives into a **strict, uniform event
schema** that every downstream consumer can rely on:

```
{
  "metric":        str,
  "role":          INPUT | OUTPUT | VALUE | COST | QUALITY | TRANSFER | UNKNOWN,
  "direction":     UPWARD | DOWNWARD | STRUCTURAL,
  "confidence":    float,
  "magnitude_pct": float,
  "zero_ratio":    float,
  "ordered_data":  bool,
  "primitive":     BIAS | DOMINANCE | TRADEOFF | REGIME_SHIFT,
  "evidence":      dict,
  "segment_context": list,
  "signal_score":  float
}
```

Five sequential gates:

1. **Identifier gate** — reject metrics matching
   `\b(id|code|key|number|no|num|pk|fk|ref|uuid|guid|sku|serial|index|idx)\b`.
2. **Temporal gate** — reject `\b(year|month|week|day|quarter|fy|fiscal)\b`.
3. **Magnitude gate** — `magnitude_pct ≥ 0.02` (relaxed mode: 0.01).
   For directional primitives, `magnitude_pct` is computed from the
   correctness layer's 30/70 split means (preferred) or the detector's
   own split, capped at 200% (anything higher is a scale artefact).
4. **Sparse gate** — `zero_ratio ≤ 0.50`.
5. **Effect-size gate** — for non-BIAS/non-DOMINANCE/non-TRADEOFF
   primitives, `delta_pct ≥ 0.005`.

**REGIME_SHIFT auto-promotion** (F-06 fix): only BIAS signals whose
relative delta exceeds 0.5 are promoted to `REGIME_SHIFT`. DOMINANCE
and TRADEOFF are never promoted.

**Role assignment** — three-tier:

1. Canonical registry (~40 names).
2. Keyword regex fallback (`revenue|sales|...` → `OUTPUT`, etc.).
3. Behavioral inference fallback from `metric_role_inference.py`
   (F-04 fix) — partially wired; resolves UNKNOWN metrics by their
   distributional signature when name-based assignment fails.

**Fail-open fallback chain:** if strict filtering produces zero events,
the engine re-runs in `relaxed=True` mode with halved magnitude
thresholds and caps any emitted event's confidence at 0.5. Per-
primitive caps (`DOMINANCE=3, BIAS=3, TRADEOFF=2, REGIME_SHIFT=2`)
prevent any single detector from flooding the synthesizer.

### 4.4 CorrectnessLayer — [`core/correctness_layer.py`]

Validates every signal **against the actual data** before it reaches
the synthesizer.

For each signal, after sorting by time column:

```
n              = len(series)
split          = ⌊0.3 · n⌋
μ_base         = mean( series[:split] )
μ_curr         = mean( series[split:] )
change         = (μ_curr − μ_base) / |μ_base|
```

Classification:

```
actual_direction = UPWARD   if change >  0.05
                 = DOWNWARD if change < −0.05
                 = FLAT     otherwise
```

Enforcement:

* `FLAT` → reject (noise).
* `detected_direction == actual_direction` → stamp as validated.
* otherwise → override detected, stamp as `corrected`.
* `STRUCTURAL` (dominance) → bypass, stamp as `validated_STRUCTURAL`
  (F-01 path).
* `μ_base ≈ 0` or `n < 20` → reject.

Other duties of this layer:

* `classify_column()` — second-tier identifier rejection using unique
  ratio (`> 0.5`), CV (`> 2.0`), and monotonicity tests.
* `compute_signed_metric_context()` — for metrics that mix positive
  and negative values, attach split sums + negative ratio so the
  synthesizer can describe net-vs-gross dynamics correctly.

The flat threshold was tightened from `±1%` to `±5%` (W1 fix) because
1% jitter on 20k-row noisy series produced false positives.

> **Caveat (F-11)** — for **unordered** data (no time column),
> `change` is set to 0, so the layer provides only FLAT rejection;
> direction validation is effectively skipped.

### 4.5 Regime Context — [`agents/canonical/regime_segmenter.py`]

Computed **alongside** primitives to add context, not signals.

**Load regime** uses tukey-style fences on historical row counts:

```
IQR  = Q3 − Q1
LOW    if  volume < median − 0.5 · IQR
HIGH   if  volume > median + 0.5 · IQR
NORMAL otherwise
```

**Stress regime** counts flags from `variance_ratio > 1.5`,
`outlier_ratio > 0.08`, `null_ratio > 0.1`; if ≥ 2 flags → `STRESSED`.

Regime tags are attached to TradeoffDetector output and read by
`SystemState` to allow silence when insights exist under only one
regime.

---

## 5. Decision Synthesis

### 5.1 DecisionSynthesizer — [`company_brain/decision_synthesizer.py`]

The synthesizer is a **pattern-matching state machine** over normalized
events. It does not see raw data — only the strict event schema. This
gives it a clean separation of concerns and makes its behaviour fully
auditable.

A second admissibility filter (`_is_trustworthy`) runs before pattern
matching, repeating the magnitude / sparsity / CV gates from the event
engine (belt-and-suspenders).

Events are grouped by `role`:

```
inputs    = events where role = INPUT
outputs   = events where role = OUTPUT
values    = events where role = VALUE
costs     = events where role = COST
quality   = events where role = QUALITY
transfers = events where role = TRANSFER
```

Patterns then fire in a priority-ordered chain. Each pattern produces
zero or one decision. Patterns:

| Pattern                | Logical condition                                              | Decision type             |
|-------------------------|----------------------------------------------------------------|---------------------------|
| Concentration risk      | any STRUCTURAL event                                            | `CONCENTRATION_RISK`      |
| Regime shift            | any `primitive == REGIME_SHIFT`                                 | `REGIME_SHIFT`            |
| Efficiency gain         | OUTPUT↑ ∧ INPUT↓ on same dataset                                | `EFFICIENCY_GAIN`         |
| Demand decline          | OUTPUT↓ (revenue/volume) ∧ corroborated by VALUE↓               | `DEMAND_DECLINE`          |
| Pricing shift           | COST↑/↓ alone OR COST drift + OUTPUT countermovement            | `PRICING_SHIFT`           |
| Quality deterioration   | QUALITY↑ (defects/churn/...)                                    | `QUALITY_DETERIORATION`   |
| Growth signal           | OUTPUT↑ ∧ VALUE↑                                                | `GROWTH_SIGNAL`           |
| Funnel breakdown        | INPUT↑ ∧ OUTPUT↓ (clicks up, conversions down)                  | `FUNNEL_BREAKDOWN`        |
| Inventory shift         | TRANSFER direction drift                                        | `INVENTORY_SHIFT`         |
| Tradeoff                | `primitive == TRADEOFF` ∧ `pair_class ∈ {TRUE_TRADEOFF,CONFLICT}` | `TRADEOFF`              |
| Unknown / fallback      | role == UNKNOWN OR no pattern matched                            | `STRUCTURAL_CHANGE`       |
| Backfill                | <3 decisions still emitted                                       | `SIGNAL_CONTEXT`          |

Each decision carries:

```
{
  "type":         <pattern name>,
  "title":        short business-language sentence,
  "summary":      multi-line paragraph,
  "decision":     recommended action sentence,
  "priority":     CRITICAL | HIGH | MEDIUM | LOW,
  "confidence":   float ∈ [0,1],
  "impact_score": float ∈ [0,1],
  "signals":      [metric names that fed this decision],
  "evidence":     dict (raw detector evidence)
}
```

**Priority scoring** (excluding F-09's hardcoded HIGH for quality,
recommended to be replaced by):

```
score = confidence · impact_score
priority = HIGH    if score ≥ 0.65
         = MEDIUM  if score ≥ 0.40
         = LOW     otherwise
```

Decisions are deduplicated by an SHA256 fingerprint over
`(type, sorted(signals), direction)`. Final sort:

```
key = ( −impact·confidence, type )
```

### 5.2 DecisionValidator — [`core/decision_validator.py`]

Validates that decisions are **stable under subsampling**:

* Bootstrap-style: draw `k = 3` random 70% subsamples (deterministic
  seed = hash of tenant + metric set).
* Re-run the relevant detector(s) on each subsample.
* `consistency_score = (k_confirming / k)`.
* Reject decisions with `consistency_score < 0.67` **unless** the
  decision is `REGIME_SHIFT` (large-effect signals are exempt to
  preserve emergency alerts).

### 5.3 CrossValidator — [`core/cross_validator.py`]

Applies **domain rules** that span multiple decisions:

* If `EFFICIENCY_GAIN` and `DEMAND_DECLINE` fire on the same revenue
  metric, downgrade the weaker one.
* If a `TRADEOFF` decision contradicts a `GROWTH_SIGNAL` (same metric
  pair, opposite sign), apply a confidence penalty.
* If a segment exhibits ≥ 20% deviation from the global direction,
  attach an attribution annotation.

> Per F-08, the confidence adjustments here (`±0.15`, `±0.25`, floors
> of 0.4 / 0.5) should ideally feed into `compute_confidence()` rather
> than mutate the score post-hoc.

### 5.4 SegmentEngine — [`core/segment_engine.py`]

Decomposes validated signals along categorical dimensions to provide
**WHERE attribution**.

For each `(dimension, value)` group with `≥ 50` rows:

```
deviation = (μ_segment − μ_global) / μ_global
```

* If `|deviation| ≥ 0.10` (F-13 alignment) → attach as
  `segment_context` on the signal.
* If a metric's per-segment deviations are uniform
  (`CV(deviations) < 0.30`) → mark as **global effect**, not a
  segment finding.
* Top-3 segments per signal, max 5 dimensions, max 5 segments per
  dimension.

A parallel function `generate_segment_decisions()` emits separate
`SEGMENT_RISK` / `SEGMENT_OPPORTUNITY` decisions at a tighter 5%
deviation threshold (used by RelativeIntelligence).

### 5.5 InsightLayer — [`core/insight_layer.py`]

Converts the validated decision set into **business-flavoured
insights** consumed by the chatbot and UI. Categories:

* `RISK` — high-priority QUALITY_DETERIORATION or DEMAND_DECLINE.
* `TRADEOFF` — surfaces TRUE_TRADEOFF/CONFLICT pairs.
* `LEAKAGE` — INPUT↑ without OUTPUT↑ (waste).
* `OPPORTUNITY` — VALUE↑ in a small segment that could be scaled.

### 5.6 RelativeIntelligence — [`core/relative_intelligence.py`]

Final, segment-vs-global comparison layer. Produces:

```
{ "type": GLOBAL_EFFECT | SEGMENT_RISK | SEGMENT_OPPORTUNITY |
          UNIFORM_PERFORMANCE,
  "metric": ...,
  "deviation": float,
  "priority": ...,
  "insight": str,
  "action": str }
```

Uses the deviation calculations from SegmentEngine.

### 5.7 Decision Compression — [`api/routes.py:138`]

Final ranking step before serialization. Merges three sources
(`global_decisions`, `aegis_insights`, `relative_decisions`) into a
single ranked top-5 list using a four-key sort:

```
key = ( type_rank, priority_rank, −impact, −confidence )
```

`type_rank` is a hand-tuned dictionary giving REGIME_SHIFT priority 0,
EFFICIENCY/DEMAND/QUALITY/FUNNEL priority 1, etc.

Deduplication is by lowercased metric set — the first occurrence of a
metric wins.

---

## 6. Persistence & Telemetry

### 6.1 EventStore — [`spine/event_store.py`]

SQLite (WAL mode) with four tables:

* `events(ts, tenant, domain, metric, value, confidence)`
* `monitoring_windows(tenant, domain, metric, window_start, window_end, mean)`
* `domain_config(tenant, domain, primary_metric, regime_window_size, slope_threshold, volatility_threshold, volatility_delta_threshold)`
* `domain_windows(tenant, domain, window_start, window_end, domain_mean, slope_pct, volatility_pct, volatility_delta, regime_candidate, regime_confirmed)`

Every row that hits the API is decomposed into per-metric events and
ingested through `EventStore.write()`. Composite timestamps (e.g.
`Year=2024, Month=07`) are constructed to `pd.Period('M')` and
back-filled monthly so domain-level windowing works regardless of
whether the source CSV has an explicit timestamp column.

### 6.2 Regime Engine (event store) — [`spine/event_store.py:239`]

For each new domain window:

1. Pull last `N` window means (`N = 8` default).
2. Compute least-squares slope:
   `β = (n·Σxy − Σx·Σy) / (n·Σx² − (Σx)²)`.
3. `slope_pct = β / mean(window_means)`.
4. `volatility_pct = std(means) / mean(means)`.
5. `vol_delta = volatility_pct − prev_volatility_pct`.

Regime classification (priority order):

```
CHAOTIC   if vol_delta > vol_delta_th AND volatility > vol_th
VOLATILE  if volatility > vol_th
DECLINE   if slope_pct < −slope_th
GROWTH    if slope_pct >  slope_th
STABLE    otherwise
BASELINE_BUILDING  if fewer than N windows exist
```

Defaults: `slope_th = 0.02, vol_th = 0.05, vol_delta_th = 0.02`. The
`regime_confirmed` field requires two consecutive matching candidates
before changing — hysteresis to avoid flapping.

### 6.3 Cognitive Snapshots — [`services/cognitive_snapshot_service.py`]

After every successful analysis, a `CognitiveSnapshot` is written that
captures:
* system state,
* full insight list with confidences,
* final decisions,
* lineage IDs back to the raw upload.

Used by the explainer (`services/decision_explainer.py`) to answer
"why did AEGIS say X on 2026-03-12?" by replaying the snapshot.

### 6.4 Memory Tiers — [`memory/`]

* `pg_memory.py` — durable per-tenant Postgres state.
* `semantic_memory_store.py` — column mapping cache.
* `shadow_baseline_store.py` — pending baselines awaiting promotion.
* `regime_stability_buffer.py` — rolling regime smoother.
* `baseline_model_store.py` — Prophet / TCN model artefacts.

### 6.5 Quarantine — [`quarantine/`]

Datasets that fail `schema_contracts.py` (column count, dtype
mismatches, drift > critical threshold) are routed to
`quarantine_router.py` and parked under `quarantine/dataset_registry`.
Promotion back into baselines requires manual approval via
`promotion_router.py`.

---

## 7. Optional & Adjacent Layers

### 7.1 Forecast Engine — [`company_brain/forecast_engine.py`,
`forecast_integration.py`]

Optional Prophet-based forecasting attached to the brain output. Runs
only when an explicit time column is present and a minimum history of
`>= 60` windows exists. Output is purely advisory — it does **not**
feed back into the confidence engine.

### 7.2 Patterns Layer — [`patterns/`]

* `isolation_forest.py` — anomaly detection on residuals.
* `tcn.py`, `context_tcn.py` — temporal convolutional networks used for
  short-horizon expected-value estimation.
* `consensus.py` — k-of-n voting across detectors.

> Per the documented design tension (F-12): XGBoost and SHAP
> (`company_brain/xgboost_engine.py`, `shap_validator.py`) exist for
> impact attribution. They are **fail-open** and never block the core
> deterministic path. A future refactor will excise them entirely.

### 7.3 Physics Layer — [`physics/`]

Domain-specific structural checks. For example,
`finance_physics_brain.py` enforces accounting identities like
`Revenue − Cost − Tax ≈ Profit ± tolerance` and emits a `STRUCTURAL`
violation event when balance breaks. These run in parallel with the
brain detectors and feed insights through the same event engine.

### 7.4 Agents — [`agents/`]

* **Canonical agents** — deterministic context enrichers
  (regime tagging, heartbeat watchdog, escalation throttler,
  segmented confidence gate).
* **Cognitive agents** — higher-level coordinators (consensus
  resolver, planner, root-cause, policy optimiser, risk brain).
  These call into the brain and modulate which patterns are eligible.
* **Self-healing motor** — `motor/self_healing_executor.py` retries
  failed action attempts within configured policy bounds.

### 7.5 Narration & Chatbot — [`core/narration.py`, `core/chatbot.py`]

Deterministic templated narration over the final decision set. An
LLM provider is plugged in only if `OLLAMA_URL` is configured;
otherwise the narration is fully rule-based. The chatbot answers
follow-up questions by looking up cognitive snapshots and quoting
their evidence — no free generation, no retraining.

### 7.6 LLM Provider — [`llm/ollama_provider.py`]

A thin adapter to a local Ollama instance, used only by
`SemanticMapper` (rare fallback) and the optional `narration` module.
The core decision path **never** calls the LLM.

---

## 8. API Surface

Defined in `api/main.py` and `api/routes.py`.

* `POST /api/analyze/{domain}`
  - Multipart upload of one CSV.
  - Required header: `X-API-Key`.
  - Resolves `tenant_id` via `tenant_middleware`.
  - Returns the full structured response — system state, narrative,
    insights, decisions, evidence, lineage IDs.

* `POST /api/ask/{domain}` — chatbot Q&A over the latest cognitive
  snapshot.

* `GET  /api/snapshots/{snapshot_id}` — re-fetch a prior snapshot for
  audit / explainability.

* `GET  /api/health` — liveness probe.

* `/admin/*` — protected tenant + API-key management
  (`security/admin_router.py`).

### 8.1 Sample Response Shape

```json
{
  "system_state": "INSIGHTFUL",
  "narrative":    "AEGIS detected a structural shift...",
  "final_decisions": [
    {
      "type": "EFFICIENCY_GAIN",
      "title": "...",
      "priority": "HIGH",
      "confidence": 0.78,
      "impact": 0.62,
      "signals": ["Revenue", "Ad_Spend"]
    }
  ],
  "global_decisions":   [...],
  "aegis_insights":     [...],
  "relative_decisions": [...],
  "segment_decisions":  [...],
  "evidence":           {...},
  "metadata":           { "rows": 12340, "tenant_id": "...", "snapshot_id": "..." }
}
```

All NaN / Infinity are stripped to `null` by `_sanitize_for_json()`
(routes.py:70) before serialisation. NumPy scalars are coerced to
native Python.

---

## 9. End-to-End Trace (Worked Example)

CSV (5,000 rows, columns: `Order_Date, Region, Revenue, Ad_Spend, Defect_Rate`).

1. **Profiler** — declares `Order_Date` time column, `Region`
   dimension, `Revenue / Ad_Spend / Defect_Rate` valid metrics, 0
   ignored columns.

2. **Sanitizer** — coerces `Revenue` "₹ 12,500" strings to `12500.0`;
   parses `Order_Date` as datetime.

3. **SemanticMapper** — renames `ad_cost → Ad_Spend`, etc. Caches the
   mapping for tenant `acme`.

4. **RealityReader** — computes `μ, σ, zero_ratio, ...` per metric.

5. **Baseline load** — fetches prior baseline; mean of Revenue was
   `9,800`, σ `1,200`.

6. **DriftDetector** — `mean_diff = |12500−9800| = 2700`,
   `allowed = 2·1200 = 2400`, `drift_score = 1.125` → `scale_shift`
   alert persisted.

7. **CompanyBrain V2**
   - DominanceDetector: `Region` shows `North = 0.72` coverage →
     `DOMINANCE / CATEGORICAL / Region`, signal_score `(0.72−0.6)/0.4 = 0.30`.
   - BiasDetector on `Revenue`: μ_base=9800, σ_base=1200, N=5000.
     `σ_eff = min(3·√(5000/50), 12) = 12`, `h = 14400`.
     Computed CUSUM peak `19,200`. `signal_score = (19200−14400)/14400 = 0.33`.
     `direction = UPWARD`.
   - BiasDetector on `Defect_Rate`: zero_ratio = 0.55 → skipped at
     event-engine sparse gate.
   - TradeoffDetector on `(Revenue, Ad_Spend)`: r=0.88, p<0.001.
     polarity(Revenue) = GOOD_UP, polarity(Ad_Spend) = GOOD_DOWN.
     opposite + positive → `TRUE_TRADEOFF`.

8. **ConfidenceEngine** for the Revenue bias signal:
   - N_score = log₁₀(5000/1000) / log₁₀(10) = 0.699.
   - signal_score = 0.33.
   - persistence = consistency = 0.7 (no historical data).
   - confidence = 0.25·0.699 + 0.30·0.33 + 0.20·0.7 + 0.15·0.7 −
     0.10·0 = **0.179 + 0.099 + 0.140 + 0.105 = 0.523**.
   - With effect_size and ordered_data factors = 1.0 → 0.523.
   - Below the 0.70 INSIGHTFUL gate but above 0.50 SystemState gate.

9. **SystemState** → `INSIGHTFUL` (Revenue bias clears 0.50).

10. **EventEngine** normalizes events; Revenue → `BIAS / UPWARD`,
    Region → `DOMINANCE / STRUCTURAL`, (Revenue,Ad_Spend) → `TRADEOFF / STRUCTURAL`.
    Per-primitive caps applied; all three pass.

11. **CorrectnessLayer** — verifies Revenue actually rose between the
    first 30% and last 70% slices of the sorted-by-date series.
    Stamps `validated` on Revenue, `STRUCTURAL` on Region, passes
    Tradeoff through.

12. **DecisionSynthesizer** — OUTPUT↑ (Revenue) + INPUT↑ (Ad_Spend)
    matches the *funnel* check, then evaluates *efficiency* against
    VALUE-role evidence. Tradeoff fires its own decision. Region fires
    `CONCENTRATION_RISK`.

13. **DecisionValidator** — 3 subsamples confirm Revenue↑ in 3/3 →
    `consistency_score = 1.0`.

14. **CrossValidator** — no conflicting decisions, no adjustments.

15. **SegmentEngine** — `Region=North` deviation on Revenue is +0.14
    → attached as segment context. `Region=South` deviation −0.18 →
    attached. `CV(deviations) = 0.41` → not uniform → not a global
    effect.

16. **Compression** — top decisions ranked, deduped, top-5 returned.
    Final JSON includes `system_state: INSIGHTFUL`, three decisions,
    full evidence trail, and a deterministic narration paragraph.

The whole pipeline executes in **single-digit seconds** for a 5k-row
CSV on a 4-core worker; profiling has shown the long-pole modules are
TradeoffDetector (O(M² · N) Pearson loops) and SegmentEngine
(per-dimension groupby).

---

## 10. Safety, Failure Modes, and Open Items

### 10.1 Safety architecture

* **Fail-open everywhere** — every detector and every stage is wrapped
  in `try/except` that logs and continues. A crash in one detector
  cannot kill the request.
* **Two-layer identifier filtering** — column_filter + event_engine +
  correctness_layer all reject IDs (belt-and-suspenders).
* **Deterministic sorts** — every list output is sorted by a stable
  key (`(metric, direction)` or `(−impact·confidence, type)`); reruns
  are reproducible.
* **JSON safety** — every response passes through
  `_sanitize_for_json()` to remove NaN / Inf / numpy scalars.

### 10.2 Known issues (open, tracked in AEGIS_AUDIT.md)

| ID    | Severity      | Summary                                                                 |
|-------|---------------|-------------------------------------------------------------------------|
| F-01  | CRITICAL      | Dominance polarity (partial fix — STRUCTURAL path landed)                |
| F-02  | HIGH          | Tradeoff polarity (fix landed — economic-polarity matrix in detector)    |
| F-03  | HIGH          | Confidence persistence/consistency hardcoded (mitigated 1.0 → 0.7)       |
| F-04  | HIGH          | Behavioral role inference partially wired                                 |
| F-05  | MEDIUM-HIGH   | First-upload baseline trust — no maturity gate yet                       |
| F-06  | MEDIUM-HIGH   | REGIME_SHIFT auto-promotion (fixed — BIAS-only)                          |
| F-07  | MEDIUM        | Fallback chain still speaks when brain says SILENT                       |
| F-08  | MEDIUM        | Confidence still adjusted outside confidence engine in 5+ locations      |
| F-09  | MEDIUM        | QUALITY_DETERIORATION priority hardcoded to HIGH                         |
| F-10  | MEDIUM        | NaN→0 in causal core (fixed — pairwise deletion)                         |
| F-11  | MEDIUM        | Correctness layer ineffective for unordered data                         |
| F-12  | LOW-MEDIUM    | XGBoost/SHAP exist but contradict no-ML design principle                 |
| F-13  | LOW-MEDIUM    | Segment threshold mismatch (aligned at 10% in attachment)                |

### 10.3 Why the design is defensible

1. **Auditability** — every decision carries the evidence block from
   the originating detector, the confidence inputs, and the lineage
   IDs back to the raw event. A regulator or CFO can trace any
   sentence in the narrative back to the rows that produced it.
2. **No black box** — the only stochastic components (Prophet, TCN,
   XGBoost / SHAP) are advisory and fail-open. The core decision path
   is a pure function of the input CSV plus stored baselines.
3. **Calibrated silence** — the system is explicitly engineered to
   refuse to speak when (a) data volume is too small, or (b) no signal
   crosses a defensible confidence floor. This is the single most
   important design choice for an enterprise context: false confidence
   destroys trust faster than absent insight.

---

## 11. Glossary

| Term                | Meaning                                                                     |
|---------------------|-----------------------------------------------------------------------------|
| **MIU**             | Minimum Information Unit — the row count below which AEGIS stays silent.    |
| **Primitive**       | A detector's atomic finding: BIAS, DOMINANCE, TRADEOFF, REGIME_SHIFT.        |
| **Signal score**    | A detector-internal scalar in `[0,1]` measuring strength of the primitive. |
| **Confidence**      | The 5-factor weighted score that gates whether a signal becomes a decision. |
| **System state**    | OBSERVATION / SILENT / INSIGHTFUL.                                          |
| **Role**            | INPUT / OUTPUT / VALUE / COST / QUALITY / TRANSFER / UNKNOWN.               |
| **Direction**       | UPWARD / DOWNWARD / STRUCTURAL.                                              |
| **Magnitude_pct**   | Relative |Δμ| / μ_base × 100, capped at 200%.                                |
| **CUSUM**           | Cumulative-sum sequential test used for BIAS detection.                     |
| **Cognitive snapshot** | An immutable record of a single analysis run, used for replay/audit.     |
| **Regime**          | Domain-level state: STABLE / GROWTH / DECLINE / VOLATILE / CHAOTIC.          |

---

*End of specification.*

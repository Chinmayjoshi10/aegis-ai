# AEGIS FORENSIC AUDIT

## Pipeline Flow

Production path: `aegis_ai/api/routes.py::analyze_data`.

1. Data load -> raw profiling  
   `routes.py` calls `DatasetProfiler.profile(df_raw)` in `aegis_ai/core/dataset_profiler.py`.  
   Input: raw CSV dataframe. Output: `valid_metrics`, `dimensions`, temporal fields, quality warnings.

2. Sanitization -> semantic mapping  
   `routes.py` sanitizes with `DataSanitizer.sanitize`, then maps columns through `SemanticMapper.map_columns`.  
   Input: sanitized dataframe plus profiler dimensions. Output: renamed dataframe plus mappings.

3. Reality + drift + persistence  
   `RealityReader.profile(df)` produces `current_stats`; `DriftDetector.detect_and_store` compares current stats to DB baseline; `persist_reality_snapshot` stores the current snapshot.

4. Signal detection  
   `run_company_brain_v2` runs `DominanceDetector`, `BiasDetector`, and `TradeoffDetector`, then confidence-gates candidates and resolves system state.

5. Forecast + pre-validation segment enrichment  
   `attach_forecasts_to_brain_output` runs, then `enrich_signals_with_segments` attaches global segment deviations to raw insights.

6. Decision pipeline  
   `run_decision_pipeline` runs:
   `normalize_events` -> `validate_signals` -> `DataUnderstandingLayer.run` -> `synthesize_decisions` -> `validate_decisions`.

7. Post-validation output  
   `routes.py` replaces `brain_output["insights"]` with `validated_events`, cross-validates global decisions, generates segment decisions, generates `aegis_insights`, and returns the response.

## Critical Bugs

1. **CRITICAL: Bias detection self-baselines against the current upload.**  
   `routes.py` builds `current_stats` from the same dataframe being analyzed, then passes `current_stats["numeric"]` into `run_company_brain_v2`, which passes it to `BiasDetector.detect`.  
   Cause: "historical baseline" is actually current-upload mean/std.  
   Impact: CUSUM detects row-order/distribution shape, not historical drift.

2. **CRITICAL: Semantic mapping can drop composite temporal columns before temporal backfill.**  
   `SemanticMapper.map_columns` keeps valid columns plus preserved dimensions only. `Year` and `Month` are excluded by `column_filter.py`, but they are temporal fields, not dimensions, so they may not be preserved.  
   Impact: datasets profiled as ordered can lose temporal columns before backfill and trend logic.

3. **CRITICAL: Correctness direction uses current dataset halves, not detector baseline.**  
   `correctness_layer._validate_signal_direction` splits the current dataset into first half and second half and overrides/rejects signals based on that change.  
   Impact: real historical drift can be rejected if the upload is internally flat; shuffled data can become false drift.

4. **CRITICAL: Segment engine compares segment mean to global mean, not segment history.**  
   `segment_engine.generate_segment_decisions` computes global means and segment deviations from the global mean.  
   Impact: "segment trend amplified" can really mean "segment has a higher average than the dataset."

5. **CRITICAL: Decision validation reruns a different pipeline than production.**  
   `decision_validator._get_decision_types` reruns `BiasDetector` and `DominanceDetector`, forces `ordered_data=False`, skips correctness, skips valid-metric allowlist, skips segmentation, and compares only decision type.  
   Impact: real production decisions can be removed, while wrong same-type decisions can pass.

## High Severity Issues

1. **HIGH: DataUnderstanding suppresses validated signals by raw variance/CV.**  
   `DataUnderstandingLayer.run` picks top 5 key metrics using `variance + coefficient_of_variation`; `decision_pipeline.py` then filters events to those metrics if overlap exists.  
   Impact: high-scale metrics dominate and validated lower-scale metrics disappear.

2. **HIGH: Initial confidence gate is overly blunt.**  
   `orchestrator_v2.py` drops candidates below 0.7 before downstream correction.  
   Impact: strong signals in smaller but valid uploads never reach correctness or synthesis.

3. **HIGH: `OBSERVATION`/`SILENT` state deletes insights.**  
   `run_company_brain_v2` returns no insights unless system state is `INSIGHTFUL`.  
   Impact: signal activity can exist in metadata but downstream sees no company insights.

4. **HIGH: No-signal response hides computed intelligence.**  
   `routes.py` returns early when `global_decisions` is empty and forces `company_insights: []`, `segment_decisions: {}` even though descriptive and `aegis_insights` may exist.

5. **HIGH: Drift status can be fabricated from validated signals.**  
   `routes.py` converts `STABLE` drift entries into `DRIFT_DETECTED` when a validated signal exists.  
   Impact: statistical drift and internal trend validation are conflated.

## Leakage Points

- `orchestrator_v2.py`: candidates below 0.7 are dropped before correctness validation. Severity: HIGH.
- `decision_pipeline.py`: key-metric filtering drops validated events. Severity: HIGH.
- `event_engine.py`: relaxed fallback reintroduces weak events with capped confidence after strict filters killed everything. Severity: MEDIUM.
- `decision_pipeline.py`: numeric decision impact is overwritten with generic text after preserving `impact_score`. Severity: MEDIUM.
- `decision_synthesizer.py`: filler decisions and `SIGNAL_CONTEXT` pad output toward 3 decisions. Severity: MEDIUM.
- `segment_engine.py`: only top 5 segment values by count are analyzed. Severity: MEDIUM.
- `descriptive_profiler.py`: concentration uses signed sums, which can break shares for metrics with negatives. Severity: HIGH.

## Cross-Layer Failures

- Profiler says data is ordered, but mapper can drop `Year`/`Month`, pushing the system into row-order behavior later.
- Drift detector uses DB baseline, but BiasDetector uses current-upload stats, so "baseline" means different things in different layers.
- Segment decisions are generated after decision cards, so cards cannot use final segment results.
- Cross-validator expects raw brain insights, but after validation it receives normalized events.
- Role assignment is split between semantic mapping, event engine, and synthesizer; unknown roles become generic alerts instead of being resolved upstream.

## Output Quality Problems

Outputs are weak because evidence is repeatedly compressed:

detector evidence -> normalized event -> pattern template -> validation by type -> generic fact/pattern/impact/action.

The final response often says "monitor" or "investigate" because causal and segment-specific evidence is either not computed or not wired into final decision cards.

Stakeholders would not trust the output because "historical baseline", "drift", "trend", and "segment amplification" mean different things across files.

## Fix Plan (Minimal Changes)

1. Use real baselines for `BiasDetector`.  
   Modify `routes.py` or `orchestrator_v2.py`: pass previous persisted baseline into `BiasDetector`, not `current_stats["numeric"]`. If no previous baseline exists, suppress BIAS or label it as within-upload trend.

2. Preserve temporal columns through mapping.  
   Modify `routes.py`: pass `profile.dimensions + profile.temporal_columns + [profile.year_column, profile.month_column]` as preserved columns.

3. Fix correctness temporal ordering.  
   Modify `correctness_layer.py`: parse timestamps with `pd.to_datetime`, drop invalid dates, and use year+month for composite time instead of year alone.

4. Stop hard-filtering by DataUnderstanding key metrics.  
   Modify `decision_pipeline.py`: use key metrics for ranking, not event removal.

5. Make decision validator mirror production contracts.  
   Modify `decision_validator.py`: use the same `ordered_data`, valid-metric filter, and correctness step; compare decision fingerprints/metrics, not type only.

6. Correct segment semantics.  
   Modify `segment_engine.py`: either label current logic explicitly as global cross-sectional deviation, or compute segment-local early/late baseline for validated metrics.

7. Do not override drift detector output.  
   Modify `routes.py`: attach validated signal metadata separately instead of rewriting `STABLE` to `DRIFT_DETECTED`.

## Final System Assessment

AEGIS has useful components, but the production path currently mixes three different notions of truth: current-upload statistics, historical DB baseline, and first-half/second-half validation. That makes it capable of producing confident but wrong business decisions.

The most dangerous bug is semantic: the system says "historical drift" while often using the current dataset as its own baseline. Until baseline ownership, temporal preservation, and validation equivalence are fixed, the output should be treated as exploratory diagnostics, not decision-grade intelligence.

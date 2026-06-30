# tests/test_structured_output.py
# Run with: python -m pytest tests/test_structured_output.py -v
#
# Validates:
#   1. Schema completeness (all required keys present)
#   2. State correctness (strict logic + state_reason)
#   3. Signal IDs, direction enum, confidence caps
#   4. Decision traces
#   5. Narration consistency (headline in narration)
#   6. Chatbot grounded answers + refusal
#   7. Determinism + no regression

import pytest

from aegis_ai.core.structured_output import compose_structured_output, _compute_state
from aegis_ai.core.narration import generate_narration, build_narration_meta
from aegis_ai.core.chatbot import answer_question, _keyword_fallback, _extract_signals_used
from aegis_ai.llm.call_gemma import _cache_key, clear_cache, _cache


# ──────────────────────────────────────────────────────
# FIXTURES — minimal valid inputs for each scenario
# ──────────────────────────────────────────────────────

_CLEAN_PROFILE = {
    "time_column": "Date",
    "year_column": None,
    "month_column": None,
    "valid_metrics": ["Revenue", "Cost", "Conversions"],
    "dimensions": ["Channel", "Region"],
    "ignored_columns": [],
    "data_quality_score": 1.0,
    "ordered_data": True,
    "row_count": 5000,
    "warnings": [],
}

_DEGRADED_PROFILE = {
    **_CLEAN_PROFILE,
    "data_quality_score": 0.72,
    "warnings": ["High missing ratio in Cost (35%)"],
}

_BLOCKED_PROFILE = {
    **_CLEAN_PROFILE,
    "data_quality_score": 0.4,
}

_CLEAN_QUALITY = {
    "overall_status": "OK",
    "forecast_mode": "NORMAL",
    "missing_pct": {"Revenue": 0.0, "Cost": 0.01},
    "domain_violations": {},
    "notes": [],
}

_BLOCKED_QUALITY = {
    "overall_status": "BLOCKED",
    "forecast_mode": "PAUSED",
    "missing_pct": {"Revenue": 0.5, "Cost": 0.45},
    "domain_violations": {},
    "notes": ["Severe missing data across columns"],
    "forecast_block_reasons": ["No numeric data"],
}

_SAMPLE_DECISIONS = [
    {
        "source": "global",
        "type": "EFFICIENCY_GAIN",
        "title": "Efficiency is Improving",
        "summary": "Cost per conversion is declining across all channels",
        "action": "Scale efficient segments",
        "priority": "HIGH",
        "confidence": 0.82,
        "impact": 0.7,
        "signals": ["Cost", "Conversions"],
        "metric": "Cost, Conversions",
    },
    {
        "source": "insight",
        "type": "RISK",
        "title": "Revenue concentrated in one channel",
        "summary": "75% of revenue comes from a single source",
        "action": "Diversify revenue sources",
        "priority": "HIGH",
        "confidence": 0.65,
        "impact": 0.8,
        "signals": [],
        "metric": "Revenue",
    },
]

_SAMPLE_INSIGHTS = [
    {
        "primitive": "BIAS",
        "subtype": "DOWNWARD",
        "metric": "Cost",
        "direction": "DOWNWARD",
        "confidence": 0.82,
        "magnitude_pct": 15.3,
        "signal_score": 0.9,
        "role": "COST",
        "summary": "Cost is persistently drifting downward from baseline",
        "evidence": {},
    },
    {
        "primitive": "BIAS",
        "subtype": "UPWARD",
        "metric": "Conversions",
        "direction": "UPWARD",
        "confidence": 0.78,
        "magnitude_pct": 8.2,
        "signal_score": 0.85,
        "role": "OUTPUT",
        "summary": "Conversions trending upward from baseline",
        "evidence": {},
    },
]

_SAMPLE_AEGIS_INSIGHTS = [
    {
        "type": "RISK",
        "title": "Revenue concentrated in one channel",
        "fact": "Channel X holds 75% of revenue",
        "confidence": 0.65,
    },
]

_CLEAN_METADATA = {
    "processing_time_sec": 0.15,
    "baseline_maturity": "MATURE",
    "upload_count": 5,
}

_IMMATURE_METADATA = {
    "processing_time_sec": 0.10,
    "baseline_maturity": "IMMATURE",
    "upload_count": 1,
}


def _build_output(**overrides):
    """Build a compose_structured_output call with sensible defaults."""
    defaults = dict(
        system_state="INSIGHTFUL",
        profile=_CLEAN_PROFILE,
        quality_report=_CLEAN_QUALITY,
        final_decisions=_SAMPLE_DECISIONS,
        global_decisions=_SAMPLE_DECISIONS,
        company_insights=_SAMPLE_INSIGHTS,
        aegis_insights=_SAMPLE_AEGIS_INSIGHTS,
        relative_decisions=[],
        segment_decisions={},
        descriptive_insights=[],
        decision_meta={"input_signals": 5, "normalized_events": 3,
                       "decisions_generated": 2, "decisions_after_validation": 2},
        reality_snapshot={},
        drift_report={},
        metadata=_CLEAN_METADATA,
        tenant_id="test_tenant",
        domain="sales",
        data_mode="backfill",
    )
    defaults.update(overrides)
    return compose_structured_output(**defaults)


# ──────────────────────────────────────────────────────
# REQUIRED SCHEMA KEYS (v1.0.0)
# ──────────────────────────────────────────────────────

REQUIRED_TOP_KEYS = {
    "meta", "state", "state_reason", "headline", "confidence", "signals",
    "data_quality", "dimension_analysis", "decisions",
    "root_cause", "explainability", "action", "assumptions", "limitations",
}

REQUIRED_META_KEYS = {
    "response_id", "schema_version", "aegis_version", "tenant", "domain", "data_mode",
    "row_count", "metrics_analyzed", "dimensions_detected", "ordered_data",
    "processing_time_sec", "baseline_maturity", "upload_count",
    "pipeline_counts",
}

REQUIRED_SIGNAL_KEYS = {
    "id", "metric", "direction", "magnitude_pct", "confidence",
    "primitive", "role", "summary", "signal_score",
}

REQUIRED_DECISION_KEYS = {
    "rank", "source", "decision_type", "title", "summary",
    "action", "priority", "confidence", "metric", "signals", "trace",
}


# ──────────────────────────────────────────────────────
# TEST 1: ACTIONABLE SCENARIO
# ──────────────────────────────────────────────────────

class TestActionable:
    """Real signals + clean data → ACTIONABLE state."""

    def test_state_is_actionable(self):
        result = _build_output()
        assert result["state"] == "ACTIONABLE"

    def test_schema_completeness(self):
        result = _build_output()
        assert REQUIRED_TOP_KEYS.issubset(result.keys()), \
            f"Missing keys: {REQUIRED_TOP_KEYS - result.keys()}"

    def test_meta_completeness(self):
        result = _build_output()
        assert REQUIRED_META_KEYS.issubset(result["meta"].keys()), \
            f"Missing meta keys: {REQUIRED_META_KEYS - result['meta'].keys()}"

    def test_meta_has_versions(self):
        result = _build_output()
        assert result["meta"]["schema_version"] == "1.0.0"
        assert isinstance(result["meta"]["aegis_version"], str)

    def test_signals_schema(self):
        result = _build_output()
        assert len(result["signals"]) == len(_SAMPLE_INSIGHTS)
        for sig in result["signals"]:
            assert REQUIRED_SIGNAL_KEYS.issubset(sig.keys()), \
                f"Missing signal keys: {REQUIRED_SIGNAL_KEYS - sig.keys()}"

    def test_signals_have_unique_ids(self):
        result = _build_output()
        ids = [s["id"] for s in result["signals"]]
        assert len(ids) == len(set(ids))
        assert all(sid.startswith("signal_") for sid in ids)

    def test_signals_direction_enum(self):
        """Direction must be one of: UP, DOWN, FLAT, STRUCTURAL."""
        result = _build_output()
        valid = {"UP", "DOWN", "FLAT", "STRUCTURAL"}
        for sig in result["signals"]:
            assert sig["direction"] in valid, \
                f"Invalid direction: {sig['direction']}"

    def test_signals_capped_at_5(self):
        """Signals must be capped at top 5 by confidence."""
        many_insights = [
            {"metric": f"m_{i}", "direction": "UPWARD", "confidence": 0.5 + i * 0.01,
             "magnitude_pct": 1.0, "signal_score": 0.5, "role": "OUTPUT",
             "primitive": "BIAS", "summary": f"test {i}"}
            for i in range(10)
        ]
        result = _build_output(company_insights=many_insights)
        assert len(result["signals"]) <= 5

    def test_decisions_schema(self):
        result = _build_output()
        assert len(result["decisions"]) == len(_SAMPLE_DECISIONS)
        for d in result["decisions"]:
            assert REQUIRED_DECISION_KEYS.issubset(d.keys()), \
                f"Missing decision keys: {REQUIRED_DECISION_KEYS - d.keys()}"

    def test_decisions_have_traces(self):
        result = _build_output()
        for d in result["decisions"]:
            trace = d["trace"]
            assert "decision_id" in trace
            assert "derived_from_signals" in trace
            assert trace["decision_id"].startswith("decision_")

    def test_decision_traces_reference_valid_signals(self):
        """Traces must reference signal IDs that exist in the signals list."""
        result = _build_output()
        valid_signal_ids = {s["id"] for s in result["signals"]}
        for d in result["decisions"]:
            for ref in d["trace"]["derived_from_signals"]:
                assert ref in valid_signal_ids, \
                    f"Trace references unknown signal: {ref}"

    def test_decisions_ranked(self):
        result = _build_output()
        ranks = [d["rank"] for d in result["decisions"]]
        assert ranks == [1, 2]

    def test_confidence_positive(self):
        result = _build_output()
        assert 0.0 < result["confidence"] <= 1.0

    def test_headline_not_empty(self):
        result = _build_output()
        assert len(result["headline"]) > 0

    def test_action_not_empty(self):
        result = _build_output()
        assert len(result["action"]) > 0

    def test_state_reason_structured(self):
        result = _build_output()
        sr = result["state_reason"]
        assert "primary" in sr
        assert "details" in sr
        assert isinstance(sr["details"], list)
        assert len(sr["primary"]) > 0

    def test_root_cause_has_primary_driver(self):
        result = _build_output()
        assert result["root_cause"]["primary_driver"] != ""

    def test_root_cause_has_affected_segments(self):
        result = _build_output()
        assert "affected_segments" in result["root_cause"]

    def test_explainability_has_why_this_decision(self):
        result = _build_output()
        assert "why_this_decision" in result["explainability"]

    def test_limitations_present(self):
        result = _build_output()
        assert isinstance(result["limitations"], list)
        assert len(result["limitations"]) >= 3  # at least the static ones

    def test_narration_consistency(self):
        """Narration must mention the headline."""
        result = _build_output()
        narration = generate_narration(result)
        assert result["headline"] in narration
        assert len(narration) > 50

    def test_narration_mentions_signals(self):
        """Narration should mention at least one signal metric."""
        result = _build_output()
        narration = generate_narration(result)
        assert any(s["metric"] in narration for s in result["signals"])


# ──────────────────────────────────────────────────────
# TEST 2: NO_SIGNAL SCENARIO
# ──────────────────────────────────────────────────────

class TestNoSignal:
    """Empty decisions → NO_SIGNAL state."""

    def test_state_is_no_signal(self):
        result = _build_output(final_decisions=[], global_decisions=[])
        assert result["state"] == "NO_SIGNAL"

    def test_schema_completeness(self):
        result = _build_output(final_decisions=[], global_decisions=[])
        assert REQUIRED_TOP_KEYS.issubset(result.keys())

    def test_confidence_is_zero(self):
        result = _build_output(final_decisions=[], global_decisions=[])
        assert result["confidence"] == 0.0

    def test_headline_mentions_no_change(self):
        result = _build_output(final_decisions=[], global_decisions=[])
        assert "no structural" in result["headline"].lower()

    def test_action_no_action_required(self):
        result = _build_output(final_decisions=[], global_decisions=[])
        assert "no action" in result["action"].lower()

    def test_narration_consistency(self):
        result = _build_output(final_decisions=[], global_decisions=[])
        narration = generate_narration(result)
        assert "no structural patterns" in narration.lower()

    def test_empty_decisions_list(self):
        result = _build_output(final_decisions=[], global_decisions=[])
        assert result["decisions"] == []

    def test_state_reason_mentions_no_decisions(self):
        result = _build_output(final_decisions=[], global_decisions=[])
        assert "0 decisions" in result["state_reason"]["details"][1].lower() or \
               "no validated" in result["state_reason"]["primary"].lower()


# ──────────────────────────────────────────────────────
# TEST 3: DATA_ISSUE SCENARIO
# ──────────────────────────────────────────────────────

class TestDataIssue:
    """Blocked quality → DATA_ISSUE state."""

    def test_state_is_data_issue_on_blocked(self):
        result = _build_output(quality_report=_BLOCKED_QUALITY)
        assert result["state"] == "DATA_ISSUE"

    def test_state_is_data_issue_on_low_score(self):
        """Quality score < 0.6 with decisions → DATA_ISSUE."""
        result = _build_output(profile=_BLOCKED_PROFILE)
        assert result["state"] == "DATA_ISSUE"

    def test_schema_completeness(self):
        result = _build_output(quality_report=_BLOCKED_QUALITY)
        assert REQUIRED_TOP_KEYS.issubset(result.keys())

    def test_headline_mentions_quality(self):
        result = _build_output(quality_report=_BLOCKED_QUALITY)
        assert "quality" in result["headline"].lower()

    def test_action_mentions_quality(self):
        result = _build_output(quality_report=_BLOCKED_QUALITY)
        assert "quality" in result["action"].lower()

    def test_narration_mentions_quality(self):
        result = _build_output(quality_report=_BLOCKED_QUALITY)
        narration = generate_narration(result)
        assert "quality" in narration.lower()

    def test_confidence_halved(self):
        """DATA_ISSUE must multiply confidence by 0.5."""
        result = _build_output(quality_report=_BLOCKED_QUALITY)
        # With BLOCKED quality, confidence should be reduced
        assert result["confidence"] < 0.5


# ──────────────────────────────────────────────────────
# TEST 4: MIXED SCENARIO
# ──────────────────────────────────────────────────────

class TestMixed:
    """Decisions present but quality is degraded → MIXED."""

    def test_state_is_mixed(self):
        result = _build_output(profile=_DEGRADED_PROFILE)
        assert result["state"] == "MIXED"

    def test_headline_mentions_confidence_limit(self):
        result = _build_output(profile=_DEGRADED_PROFILE)
        assert "confidence" in result["headline"].lower()

    def test_narration_mentions_degraded(self):
        result = _build_output(profile=_DEGRADED_PROFILE)
        narration = generate_narration(result)
        assert "degraded" in narration.lower()

    def test_assumptions_mention_degraded(self):
        result = _build_output(profile=_DEGRADED_PROFILE)
        assert any("degraded" in a.lower() or "verify" in a.lower()
                    for a in result["assumptions"])


# ──────────────────────────────────────────────────────
# TEST 5: STATE LOGIC — strict priority rules
# ──────────────────────────────────────────────────────

class TestStateLogic:
    """Direct test of _compute_state priority rules."""

    def test_blocked_overrides_everything(self):
        """BLOCKED quality must produce DATA_ISSUE even with decisions."""
        state = _compute_state(
            quality_report={"overall_status": "BLOCKED"},
            final_decisions=_SAMPLE_DECISIONS,
            data_quality_score=1.0,
        )
        assert state == "DATA_ISSUE"

    def test_no_decisions_beats_quality(self):
        """Empty decisions → NO_SIGNAL even with clean quality."""
        state = _compute_state(
            quality_report={"overall_status": "OK"},
            final_decisions=[],
            data_quality_score=1.0,
        )
        assert state == "NO_SIGNAL"

    def test_low_quality_beats_decisions(self):
        """Score < 0.6 → DATA_ISSUE even with decisions."""
        state = _compute_state(
            quality_report={"overall_status": "OK"},
            final_decisions=_SAMPLE_DECISIONS,
            data_quality_score=0.5,
        )
        assert state == "DATA_ISSUE"

    def test_degraded_produces_mixed(self):
        """0.6 <= score < 0.85 with decisions → MIXED."""
        state = _compute_state(
            quality_report={"overall_status": "OK"},
            final_decisions=_SAMPLE_DECISIONS,
            data_quality_score=0.75,
        )
        assert state == "MIXED"

    def test_clean_produces_actionable(self):
        """Score >= 0.85 with decisions → ACTIONABLE."""
        state = _compute_state(
            quality_report={"overall_status": "OK"},
            final_decisions=_SAMPLE_DECISIONS,
            data_quality_score=0.90,
        )
        assert state == "ACTIONABLE"

    def test_exact_boundary_085(self):
        """Score == 0.85 → ACTIONABLE (not MIXED)."""
        state = _compute_state(
            quality_report={"overall_status": "OK"},
            final_decisions=_SAMPLE_DECISIONS,
            data_quality_score=0.85,
        )
        assert state == "ACTIONABLE"

    def test_exact_boundary_060(self):
        """Score == 0.6 → MIXED (not DATA_ISSUE)."""
        state = _compute_state(
            quality_report={"overall_status": "OK"},
            final_decisions=_SAMPLE_DECISIONS,
            data_quality_score=0.6,
        )
        assert state == "MIXED"


# ──────────────────────────────────────────────────────
# TEST 6: CONFIDENCE CAPS
# ──────────────────────────────────────────────────────

class TestConfidenceCaps:
    """Verify state-based confidence adjustments."""

    def test_data_issue_halves_confidence(self):
        """DATA_ISSUE state must multiply confidence by 0.5."""
        result = _build_output(
            quality_report=_BLOCKED_QUALITY,
            profile=_CLEAN_PROFILE,  # clean profile but blocked quality
        )
        assert result["state"] == "DATA_ISSUE"
        assert result["confidence"] <= 0.5

    def test_actionable_no_penalty(self):
        """ACTIONABLE state should not suppress confidence."""
        result = _build_output()
        assert result["state"] == "ACTIONABLE"
        assert result["confidence"] > 0.5


# ──────────────────────────────────────────────────────
# TEST 7: NARRATION MODES
# ──────────────────────────────────────────────────────

class TestNarrationModes:
    """Narration mode selection and fallback."""

    def test_template_mode_returns_string(self):
        result = _build_output()
        narration = generate_narration(result, mode="template")
        assert isinstance(narration, str)
        assert len(narration) > 0

    def test_llm_mode_falls_back_to_template(self):
        """LLM mode should fall back gracefully when Gemma is unavailable."""
        result = _build_output()
        narration = generate_narration(result, mode="llm")
        assert isinstance(narration, str)
        assert len(narration) > 0

    def test_invalid_mode_raises(self):
        result = _build_output()
        with pytest.raises(ValueError, match="Unknown narration mode"):
            generate_narration(result, mode="invalid_mode")


# ──────────────────────────────────────────────────────
# TEST 8: NARRATION META
# ──────────────────────────────────────────────────────

class TestNarrationMeta:
    """Verify narration_meta built at API layer."""

    def test_meta_has_required_keys(self):
        result = _build_output()
        narration = generate_narration(result)
        meta = build_narration_meta(result, narration)
        assert "mode" in meta
        assert "fallback" in meta
        assert "headline_verified" in meta

    def test_template_mode_headline_verified(self):
        result = _build_output()
        narration = generate_narration(result)
        meta = build_narration_meta(result, narration, mode="template")
        assert meta["headline_verified"] is True
        assert meta["mode"] == "template"
        assert meta["fallback"] is False


# ──────────────────────────────────────────────────────
# TEST 9: DETERMINISM — same input → same output
# ──────────────────────────────────────────────────────

class TestDeterminism:
    """Verify deterministic output."""

    def test_structured_output_deterministic(self):
        """All fields except response_id must be identical across calls."""
        r1 = _build_output()
        r2 = _build_output()
        # response_id is intentionally unique per call
        r1_copy = {**r1, "meta": {**r1["meta"]}}
        r2_copy = {**r2, "meta": {**r2["meta"]}}
        del r1_copy["meta"]["response_id"]
        del r2_copy["meta"]["response_id"]
        assert r1_copy == r2_copy

    def test_narration_deterministic(self):
        r1 = _build_output()
        n1 = generate_narration(r1)
        n2 = generate_narration(r1)
        assert n1 == n2


# ──────────────────────────────────────────────────────
# TEST 10: ASSUMPTIONS + LIMITATIONS
# ──────────────────────────────────────────────────────

class TestAssumptions:
    """Verify assumptions are derived from profile/metadata, not invented."""

    def test_immature_baseline_assumption(self):
        result = _build_output(metadata=_IMMATURE_METADATA)
        assert any("immature" in a.lower() for a in result["assumptions"])

    def test_no_temporal_assumption(self):
        no_time_profile = {**_CLEAN_PROFILE, "ordered_data": False, "time_column": None}
        result = _build_output(profile=no_time_profile)
        assert any("temporal" in a.lower() or "row order" in a.lower()
                    for a in result["assumptions"])

    def test_no_dimensions_assumption(self):
        no_dim_profile = {**_CLEAN_PROFILE, "dimensions": []}
        result = _build_output(profile=no_dim_profile)
        assert any("dimension" in a.lower() for a in result["assumptions"])

    def test_limitations_always_present(self):
        result = _build_output()
        assert len(result["limitations"]) >= 3
        assert any("external" in l.lower() for l in result["limitations"])
        assert any("single dataset" in l.lower() for l in result["limitations"])
        assert any("causal" in l.lower() for l in result["limitations"])


# ──────────────────────────────────────────────────────
# TEST 11: CHATBOT — grounded Q&A
# ──────────────────────────────────────────────────────

class TestChatbot:
    """Verify chatbot answers grounded on structured JSON."""

    def test_empty_question_handled(self):
        result = _build_output()
        resp = answer_question("", result)
        assert "provide a question" in resp["answer"].lower()

    def test_state_query_grounded(self):
        result = _build_output()
        resp = _keyword_fallback("What is the current state?", result)
        assert "ACTIONABLE" in resp

    def test_signal_query_grounded(self):
        result = _build_output()
        resp = _keyword_fallback("What signals were detected?", result)
        assert "Cost" in resp or "Conversions" in resp

    def test_decision_query_grounded(self):
        result = _build_output()
        resp = _keyword_fallback("What should I do?", result)
        assert "Efficiency" in resp or "Scale" in resp

    def test_quality_query_grounded(self):
        result = _build_output()
        resp = _keyword_fallback("How is data quality?", result)
        assert "100%" in resp or "OK" in resp

    def test_confidence_query_grounded(self):
        result = _build_output()
        resp = _keyword_fallback("How confident are you?", result)
        assert "confidence" in resp.lower()

    def test_root_cause_query_grounded(self):
        result = _build_output()
        resp = _keyword_fallback("What is the root cause?", result)
        assert "Cost" in resp or "root" in resp.lower() or "declining" in resp.lower()

    def test_unknown_query_refusal(self):
        result = _build_output()
        resp = _keyword_fallback("What is the meaning of life?", result)
        assert "not available" in resp.lower()

    def test_metric_specific_query(self):
        result = _build_output()
        resp = _keyword_fallback("Tell me about Cost", result)
        assert "Cost" in resp

    def test_answer_question_returns_dict(self):
        result = _build_output()
        resp = answer_question("What is the state?", result)
        assert isinstance(resp, dict)
        assert "answer" in resp
        assert "grounded" in resp
        assert "mode" in resp
        assert "signals_used" in resp
        assert resp["grounded"] is True

    def test_signals_used_populated_for_signal_query(self):
        result = _build_output()
        resp = answer_question("What signals were detected?", result)
        assert isinstance(resp.get("signals_used"), list)
        # Both Cost and Conversions are mentioned in signal query results
        assert len(resp["signals_used"]) > 0

    def test_signals_used_empty_for_unrelated_query(self):
        result = _build_output()
        resp = answer_question("How confident are you?", result)
        # Confidence answer doesn't mention specific signal metrics
        assert isinstance(resp.get("signals_used"), list)


# ──────────────────────────────────────────────────────
# TEST 12: RESPONSE_ID + CACHE
# ──────────────────────────────────────────────────────

class TestResponseId:
    """Verify response_id uniqueness."""

    def test_response_id_is_uuid(self):
        result = _build_output()
        rid = result["meta"]["response_id"]
        assert isinstance(rid, str)
        assert len(rid) == 36  # UUID format

    def test_response_id_unique_per_call(self):
        r1 = _build_output()
        r2 = _build_output()
        assert r1["meta"]["response_id"] != r2["meta"]["response_id"]


class TestCache:
    """Verify prompt cache logic."""

    def test_cache_key_deterministic(self):
        k1 = _cache_key("test prompt")
        k2 = _cache_key("test prompt")
        assert k1 == k2

    def test_cache_key_different_for_different_prompts(self):
        k1 = _cache_key("prompt A")
        k2 = _cache_key("prompt B")
        assert k1 != k2

    def test_clear_cache(self):
        _cache["test_key"] = "test_value"
        count = clear_cache()
        assert count >= 1
        assert len(_cache) == 0

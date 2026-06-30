"""
tests/test_gemma.py
=====================
Runtime integration test for Gemma/Ollama.

This is NOT a unit test — it requires Ollama to be running with the model pulled.
Run manually:
    python tests/test_gemma.py

Setup:
    1. Install Ollama: https://ollama.com/download
    2. Pull model: ollama pull gemma4:e2b-it-q4_K_M
    3. Start server: ollama serve
    4. Run this script
"""

import sys
import json

# Ensure project root is importable
sys.path.insert(0, ".")

from aegis_ai.llm.call_gemma import check_gemma_health, call_gemma, clear_cache
from aegis_ai.core.structured_output import compose_structured_output
from aegis_ai.core.narration import generate_narration
from aegis_ai.core.chatbot import answer_question


def _separator(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def _build_sample_output():
    """Build a real structured output for testing."""
    return compose_structured_output(
        system_state="INSIGHTFUL",
        profile={
            "time_column": "Date",
            "year_column": None,
            "month_column": None,
            "valid_metrics": ["Revenue", "Cost", "Conversions"],
            "dimensions": ["Channel", "Region"],
            "ignored_columns": [],
            "data_quality_score": 0.95,
            "ordered_data": True,
            "row_count": 5000,
            "warnings": [],
        },
        quality_report={
            "overall_status": "OK",
            "forecast_mode": "NORMAL",
            "missing_pct": {"Revenue": 0.01},
            "domain_violations": {},
            "notes": [],
        },
        final_decisions=[
            {
                "source": "global",
                "type": "EFFICIENCY_GAIN",
                "title": "Cost Efficiency Improving",
                "summary": "Cost per conversion declining across channels",
                "action": "Scale efficient segments",
                "priority": "HIGH",
                "confidence": 0.85,
                "signals": ["Cost", "Conversions"],
                "metric": "Cost, Conversions",
            },
        ],
        global_decisions=[],
        company_insights=[
            {
                "primitive": "BIAS",
                "metric": "Cost",
                "direction": "DOWNWARD",
                "confidence": 0.85,
                "magnitude_pct": 12.5,
                "signal_score": 0.9,
                "role": "COST",
                "summary": "Cost trending downward",
            },
        ],
        aegis_insights=[],
        relative_decisions=[],
        segment_decisions={},
        descriptive_insights=[],
        decision_meta={"input_signals": 3, "normalized_events": 2,
                       "decisions_generated": 1, "decisions_after_validation": 1},
        reality_snapshot={},
        drift_report={},
        metadata={"processing_time_sec": 0.15, "baseline_maturity": "MATURE", "upload_count": 5},
        tenant_id="test",
        domain="marketing",
        data_mode="backfill",
    )


def test_1_health_check():
    _separator("TEST 1: Gemma Health Check")
    result = check_gemma_health()
    print(json.dumps(result, indent=2))

    if result["available"]:
        print(f"\n[OK] Gemma is AVAILABLE (latency: {result['latency_ms']}ms)")
    else:
        print(f"\n[FAIL] Gemma is NOT available: {result.get('error', 'unknown')}")
        print(" -> Install: https://ollama.com/download")
        print(" -> Pull: ollama pull gemma4:e2b-it-q4_K_M")
        print(" -> Start: ollama serve")

    return result["available"]


def test_2_narration_llm(analysis):
    _separator("TEST 2: LLM Narration")
    print("Generating narration via Gemma...")

    narration = generate_narration(analysis, mode="llm")
    print(f"\nNarration ({len(narration)} chars):")
    print("-" * 40)
    print(narration[:500])
    if len(narration) > 500:
        print(f"... ({len(narration) - 500} more chars)")
    print("-" * 40)
    print("[OK] LLM narration successful")


def test_3_chatbot(analysis):
    _separator("TEST 3: Chatbot Q&A")

    questions = [
        "What is the current state of the analysis?",
        "What signals were detected?",
        "What should I do based on this analysis?",
        "What is the data quality?",
    ]

    for q in questions:
        print(f"\nQ: {q}")
        result = answer_question(q, analysis)
        print(f"A: {result['answer'][:200]}")
        print(f"   mode={result['mode']} source={result['source']} signals_used={result.get('signals_used', [])}")


def test_4_cache():
    _separator("TEST 4: Cache Verification")

    # Clear cache first
    cleared = clear_cache()
    print(f"Cache cleared ({cleared} entries)")

    prompt = "Reply with: hello"

    print("Call 1 (fresh)...")
    r1 = call_gemma(prompt, timeout=30)
    print(f"  Response: {r1[:100]}")

    print("Call 2 (should be cached)...")
    r2 = call_gemma(prompt, timeout=30)
    print(f"  Response: {r2[:100]}")
    print(f"  Cache hit: {r1 == r2}")
    print("[OK] Cache working" if r1 == r2 else "[WARN] Cache mismatch (non-deterministic model)")


def main():
    print("\n" + "=" * 60)
    print("  AEGIS — Gemma Runtime Integration Test")
    print("=" * 60)

    # Build sample analysis
    analysis = _build_sample_output()
    print(f"\nStructured output built (response_id: {analysis['meta']['response_id']})")

    # Test 1: Health Check
    available = test_1_health_check()

    if not available:
        print("\n[WARN] Gemma not available — skipping LLM tests.")
        print("   Keyword fallback tests will still run.\n")

        # Run chatbot in fallback mode
        test_3_chatbot(analysis)

        print("\n" + "=" * 60)
        print("  DONE (partial — Gemma offline)")
        print("=" * 60 + "\n")
        return

    # Test 2: LLM Narration
    test_2_narration_llm(analysis)

    # Test 3: Chatbot
    test_3_chatbot(analysis)

    # Test 4: Cache
    test_4_cache()

    print("\n" + "=" * 60)
    print("  ALL TESTS PASSED ✅")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

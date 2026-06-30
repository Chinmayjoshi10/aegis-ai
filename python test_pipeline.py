from aegis_ai.core.decision_pipeline import run_decision_pipeline

insights = [
    {
        "metric": "Clicks",
        "direction": "UPWARD",
        "confidence": 0.8,
        "magnitude_pct": 0.12,
        "role": "INPUT"
    },
    {
        "metric": "Conversions",
        "direction": "DOWNWARD",
        "confidence": 0.9,
        "magnitude_pct": 0.15,
        "role": "OUTPUT"
    },
    {
        "metric": "Revenue",
        "direction": "DOWNWARD",
        "confidence": 0.85,
        "magnitude_pct": 0.10,
        "role": "VALUE"
    }
]

result = run_decision_pipeline(insights)

print(result)
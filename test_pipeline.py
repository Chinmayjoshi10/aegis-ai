"""Quick pipeline validation script."""
import requests, json

r = requests.post(
    "http://127.0.0.1:8011/api/analyze/marketing",
    headers={"X-API-Key": "shadowcorp-key"},
    files={"file": open("Aegis_Stress_Test_Dataset.csv", "rb")},
)
d = r.json()

print("=" * 60)
print("STATUS:", d.get("status"))
print("DECISIONS:", len(d.get("global_decisions", [])))

dm = d.get("decision_meta", {})
print("\n--- DECISION META ---")
for k in ["input_signals", "filtered_events", "decisions_generated", "decisions_after_validation"]:
    print(f"  {k}: {dm.get(k)}")

print("\n--- GLOBAL DECISIONS ---")
for i, x in enumerate(d.get("global_decisions", [])):
    print(f"  [{i+1}] {x.get('type')}: {x.get('title')}")

qr = d.get("quality_report", {})
print("\n--- QUALITY ---")
print("  domain_violations:", qr.get("domain_violations", {}))
print("  data_quality_score:", qr.get("data_quality_score", "N/A"))

print("\n--- AEGIS INSIGHTS ---")
for i, x in enumerate(d.get("aegis_insights", [])):
    print(f"  [{i+1}] {x.get('type')}: {x.get('title', '')[:100]}")

print("=" * 60)

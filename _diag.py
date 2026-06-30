import json, subprocess, sys

r = subprocess.run(
    ["curl.exe", "-s", "-X", "POST",
     "http://127.0.0.1:8000/api/analyze/sales",
     "-H", "X-API-Key: shadowcorp-key",
     "-F", "file=@Sales Transaction v.4a.csv"],
    capture_output=True, cwd=r"C:\Users\chinm\aegis_ai"
)
d = json.loads(r.stdout)

print("AEGIS INSIGHTS:")
for i in d.get("aegis_insights", []):
    print(f"  [{i['type']}] {i['title'][:70]}")

print()
print("SEGMENT DECISIONS + COVERAGE:")
total = d.get("profile", {}).get("row_count", 1)
for k, v in d.get("segment_decisions", {}).items():
    for ctx in v:
        m    = ctx.get("metric", "?")
        dev  = ctx.get("deviation", "?")
        rows = ctx.get("segment_rows", 0)
        cov  = round(rows / total * 100, 2) if isinstance(rows, int) else "?"
        gdir = ctx.get("global_direction", "?")
        print(f"  {k}: {m} gdir={gdir} dev={dev} rows={rows} cov={cov}%")

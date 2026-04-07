from aegis_ai.spine.event_store import EventStore

store = EventStore("aegis_events.db")

rows = store.db.execute("""
SELECT
    window_start,
    domain_mean,
    slope_pct,
    volatility_pct,
    regime_candidate,
    regime_confirmed
FROM domain_windows
ORDER BY window_start
""").fetchall()

print("\n---- ALL WINDOWS ----\n")

for r in rows:
    print(r)

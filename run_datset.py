import pandas as pd

from aegis_ai.brains.reality_reader import RealityReader
from aegis_ai.company_brain.tradeoff_detector import TradeoffDetector
from aegis_ai.company_brain.system_state import resolve_system_state
from aegis_ai.company_brain.trajectory import TrajectoryEngine

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------
CSV_PATH = r"C:\Users\chinm\aegis_ai\archive (8)\DataCoSupplyChainDataset.csv"

# ---------------------------------------------------
# LOAD DATA (FIXED ENCODING)
# ---------------------------------------------------
print("Loading dataset...")
df = pd.read_csv(CSV_PATH, encoding="latin1")
print(f"Loaded dataset with {len(df)} rows and {len(df.columns)} columns")

# ---------------------------------------------------
# REALITY SNAPSHOT
# ---------------------------------------------------
print("\n=== REALITY SNAPSHOT ===")
reader = RealityReader()
reality = reader.profile(df)

print("Regime detected:")
print(reality.get("regime"))

print("\nNumeric columns profiled:", len(reality.get("numeric_columns", [])))
print("Issues detected:", len(reality.get("issues", [])))

# ---------------------------------------------------
# TRADEOFF DETECTION (RAW CANDIDATES)
# ---------------------------------------------------
print("\n=== TRADEOFF DETECTION ===")
detector = TradeoffDetector()

tradeoffs = detector.detect(
    df=df,
    metric_stats=reality["stats"],
    regime=reality.get("regime"),
)

print(f"Tradeoff candidates detected: {len(tradeoffs)}")

for i, t in enumerate(tradeoffs[:5]):
    print(f"\nCandidate {i+1}:")
    print(t)

# ---------------------------------------------------
# CONFIDENCE + SYSTEM STATE
# NOTE:
# We intentionally use conservative confidence
# to test silence discipline
# ---------------------------------------------------
print("\n=== SYSTEM STATE RESOLUTION ===")

insights = []
for t in tradeoffs:
    t["confidence"] = t.get("signal_score", 0.0)
    insights.append(t)

state = resolve_system_state(
    row_count=len(df),
    insights=insights,
)

print("System State:", state)

# ---------------------------------------------------
# TRAJECTORY (SIMULATED, NO HISTORY)
# ---------------------------------------------------
print("\n=== TRAJECTORY SAMPLE ===")

trajectory_engine = TrajectoryEngine()
annotated = trajectory_engine.annotate(
    insights=insights,
    insight_history=[],
)

if annotated:
    print("Trajectory for first insight:")
    print(annotated[0].get("trajectory"))
else:
    print("No insights to attach trajectory")

# ---------------------------------------------------
# FINAL SUMMARY
# ---------------------------------------------------
print("\n=== SUMMARY ===")
print(f"Rows: {len(df)}")
print(f"Regime: {reality.get('regime')}")
print(f"Tradeoff candidates: {len(tradeoffs)}")
print(f"System State: {state}")

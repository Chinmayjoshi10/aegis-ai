import pkgutil
import importlib
import traceback
import time

import aegis_ai

failed = []
slow = []

for module in pkgutil.walk_packages(aegis_ai.__path__, aegis_ai.__name__ + "."):
    start = time.time()
    try:
        importlib.import_module(module.name)
        duration = time.time() - start
        print(f"[OK] {module.name} ({duration:.3f}s)")
        if duration > 1.0:
            slow.append((module.name, duration))
    except Exception:
        print(f"[FAIL] {module.name}")
        traceback.print_exc()
        failed.append(module.name)

print("\n====================")
print("FAILED MODULES:")
for f in failed:
    print(f)

print("\nSLOW MODULES (>1s):")
for name, dur in slow:
    print(f"{name} - {dur:.3f}s")

print("====================")
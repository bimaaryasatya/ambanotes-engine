import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.db import logs_col

print("--- 100 LATEST WORKSPACE LOGS ---")
logs = list(logs_col.find().sort("timestamp", -1).limit(100))
for l in logs:
    print(f"[{l.get('timestamp')}] {l.get('service')} - {l.get('action')}: {l.get('message')} (Metadata: {l.get('metadata')})")

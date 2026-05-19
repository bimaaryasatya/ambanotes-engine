import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.db import logs_col

query = {
    "message": {"$regex": "gagal|error|failed|400|invalid|miss", "$options": "i"}
}

logs = list(logs_col.find(query).sort("timestamp", -1))
for idx in range(min(18, len(logs))):
    l = logs[idx]
    print(f"{idx+1}. [{l.get('timestamp')}] {l.get('service')} - {l.get('action')}: {l.get('message')}")

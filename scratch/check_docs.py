import sys
import os
from bson.objectid import ObjectId

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.db import users_col, docs_col

print("--- AUDITING USER GOOGLE DRIVE STATE ---")
user = users_col.find_one({"username": "bimazznxt"})
if not user:
    print("User bimazznxt not found.")
else:
    print(f"User ID: {user['_id']}")
    print(f"Google Drive Connected: {user.get('google_drive_connected')}")
    oauth = user.get('google_oauth', {})
    print(f"Has Access Token: {bool(oauth.get('access_token'))}")
    print(f"Has Refresh Token: {bool(oauth.get('refresh_token'))}")
    print(f"OAuth keys present: {list(oauth.keys())}")

print("\n--- AUDITING DOCUMENTS FOR bimazznxt ---")
if user:
    user_id_str = str(user['_id'])
    all_docs = list(docs_col.find({"uploaded_by": user_id_str}))
    print(f"Total documents owned: {len(all_docs)}")
    
    docs_to_migrate = list(docs_col.find({
        "uploaded_by": user_id_str,
        "file_data": {"$exists": True, "$ne": None},
        "google_drive": None
    }))
    print(f"Documents pending migration (have file_data, no google_drive): {len(docs_to_migrate)}")
    
    for idx, doc in enumerate(docs_to_migrate[:5]):
        print(f"  {idx+1}. doc_id: {doc.get('doc_id')}, filename: {doc.get('filename')}, file_data (size): {len(doc.get('file_data')) if doc.get('file_data') else 0}")

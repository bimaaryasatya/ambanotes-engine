import os
import sys
import json
from datetime import datetime

# Set up paths
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_gateway.api import app
from common.db import chats_col, users_col, docs_col
from common.jwt_utils import generate_token
from bson.objectid import ObjectId

def run_test():
    print("=== STARTING INTEGRATION TEST FOR CHAT STORAGE ===")
    
    # 1. Create a dummy user and a dummy document for clean isolation
    test_user_id = ObjectId()
    test_org_id = "test-org-123"
    test_user = {
        "_id": test_user_id,
        "username": "test_chat_user",
        "role": "owner",
        "org_id": test_org_id
    }
    
    test_doc_id = "test-doc-uuid-999"
    test_doc = {
        "doc_id": test_doc_id,
        "filename": "laporan_keuangan_2026.pdf",
        "content": "Ini adalah laporan keuangan perusahaan tahun 2026.",
        "org_id": test_org_id,
        "uploaded_by": str(test_user_id)
    }
    
    # Insert dummy user & doc into DB
    users_col.insert_one(test_user)
    docs_col.insert_one(test_doc)
    print(f"Inserted test user with ID: {test_user_id} and test doc with doc_id: {test_doc_id}")
    
    # Clean up any existing chat for this test key
    chats_col.delete_many({"user_id": str(test_user_id), "doc_id": test_doc_id})
    
    token = generate_token(test_user)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    client = app.test_client()
    
    try:
        # --- TEST 1: Post a first message to `/chat` ---
        print("\n--- Test 1: Sending first message to /ai/chat ---")
        payload1 = {
            "message": "Halo, sebutkan tahun dari laporan keuangan ini.",
            "context": test_doc["content"],
            "doc_id": test_doc_id
        }
        response1 = client.post("/ai/chat", headers=headers, data=json.dumps(payload1))
        print(f"Response status: {response1.status_code}")
        data1 = json.loads(response1.data)
        print(f"Response data: {data1}")
        
        assert response1.status_code == 200, "Expected status code 200"
        assert "answer" in data1, "Expected 'answer' in response"
        assert "history" in data1, "Expected 'history' in response"
        assert len(data1["history"]) == 2, "Expected history length to be 2"
        
        # Verify db entry was created
        db_chat = chats_col.find_one({"user_id": str(test_user_id), "doc_id": test_doc_id})
        assert db_chat is not None, "Chat document was not saved to MongoDB"
        print(f"Verified MongoDB record exists. Message history: {db_chat['chat_json']}")
        
        # --- TEST 2: Post a second message to `/chat` with empty history parameter ---
        # It should load history from DB, call model, and update DB.
        print("\n--- Test 2: Sending second message to /ai/chat (loads from DB) ---")
        payload2 = {
            "message": "Siapa yang mengunggah dokumen ini?",
            "doc_id": test_doc_id
        }
        response2 = client.post("/ai/chat", headers=headers, data=json.dumps(payload2))
        print(f"Response status: {response2.status_code}")
        data2 = json.loads(response2.data)
        print(f"Response data: {data2}")
        
        assert response2.status_code == 200
        assert len(data2["history"]) == 4, "Expected history length to be 4 after turn 2"
        
        # --- TEST 3: Get list of chats from `/chats` ---
        print("\n--- Test 3: Fetching chat list from /ai/chats ---")
        response3 = client.get("/ai/chats", headers=headers)
        print(f"Response status: {response3.status_code}")
        chats_list = json.loads(response3.data)
        print(f"Chats list: {chats_list}")
        
        assert response3.status_code == 200
        assert len(chats_list) >= 1, "Expected at least 1 chat in the list"
        chat_entry = next((c for c in chats_list if c["doc_id"] == test_doc_id), None)
        assert chat_entry is not None, "Test doc chat not found in chat list"
        assert chat_entry["filename"] == "laporan_keuangan_2026.pdf", "Joined filename is incorrect"
        
        # --- TEST 4: Get chat detail from `/chat/<doc_id>` ---
        print("\n--- Test 4: Fetching chat detail from /ai/chat/<doc_id> ---")
        response4 = client.get(f"/ai/chat/{test_doc_id}", headers=headers)
        print(f"Response status: {response4.status_code}")
        chat_detail = json.loads(response4.data)
        print(f"Chat detail: {chat_detail}")
        
        assert response4.status_code == 200
        assert chat_detail["doc_id"] == test_doc_id
        assert chat_detail["filename"] == "laporan_keuangan_2026.pdf"
        assert len(chat_detail["chat_json"]) == 4
        
        print("\n=== ALL TESTS PASSED SUCCESSFULLY ===")
        
    finally:
        # Cleanup
        print("\n--- Cleaning up test records ---")
        users_col.delete_one({"_id": test_user_id})
        docs_col.delete_one({"doc_id": test_doc_id})
        chats_col.delete_many({"user_id": str(test_user_id), "doc_id": test_doc_id})
        print("Cleanup completed.")

if __name__ == "__main__":
    run_test()

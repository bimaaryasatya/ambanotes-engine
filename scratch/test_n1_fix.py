import os
import sys
import json
from datetime import datetime

# Set up paths
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_gateway.api import app
from common.db import users_col, docs_col, delegations_col, assets_col
from common.jwt_utils import generate_token
from bson.objectid import ObjectId

def run_test():
    print("=== STARTING INTEGRATION TEST FOR N+1 QUERY FIXES ===")
    
    # 1. Create a dummy organization and user
    test_org_id = "test-org-n1-fix"
    test_user_id = ObjectId()
    
    test_user = {
        "_id": test_user_id,
        "user_id": str(test_user_id),
        "username": "test_n1_user",
        "email": "n1_test@example.com",
        "role": "owner",
        "org_id": test_org_id
    }
    
    # Create two test divisions/delegations
    del_id_1 = ObjectId()
    del_id_2 = ObjectId()
    
    delegation_1 = {
        "_id": del_id_1,
        "name": "Dinas Kebersihan",
        "org_id": test_org_id,
        "created_at": datetime.utcnow()
    }
    
    delegation_2 = {
        "_id": del_id_2,
        "name": "Dinas Pekerjaan Umum",
        "org_id": test_org_id,
        "created_at": datetime.utcnow()
    }
    
    # Create a member under delegation_1
    member_user_id = ObjectId()
    member_user = {
        "_id": member_user_id,
        "user_id": str(member_user_id),
        "username": "member_dinas_kebersihan",
        "email": "member_kebersihan@example.com",
        "role": "member",
        "org_id": test_org_id,
        "delegation_id": str(del_id_1)
    }

    # Create documents assigned to delegations
    doc_1_id = "doc-uuid-kebersihan"
    doc_2_id = "doc-uuid-pu"
    
    doc_1 = {
        "doc_id": doc_1_id,
        "filename": "surat_sampah.pdf",
        "title": "Surat Pengelolaan Sampah",
        "org_id": test_org_id,
        "delegation_id": str(del_id_1),
        "uploaded_by": str(test_user_id),
        "status": "processed"
    }
    
    doc_2 = {
        "doc_id": doc_2_id,
        "filename": "surat_jalan.pdf",
        "title": "Surat Perbaikan Jalan",
        "org_id": test_org_id,
        "delegation_id": str(del_id_2),
        "uploaded_by": str(test_user_id),
        "status": "processed"
    }
    
    # Create assets for delegations
    asset_1_id = ObjectId()
    asset_2_id = ObjectId()
    
    asset_1 = {
        "_id": asset_1_id,
        "type": "letterhead",
        "org_id": test_org_id,
        "name": "Kop Dinas Kebersihan",
        "delegation_id": str(del_id_1),
        "image_data": "base64dummydata1",
        "is_active": True
    }
    
    asset_2 = {
        "_id": asset_2_id,
        "type": "signature",
        "org_id": test_org_id,
        "name": "TTD Kepala PU",
        "delegation_id": str(del_id_2),
        "image_data": "base64dummydata2",
        "is_active": True
    }

    print("Inserting test fixtures...")
    users_col.insert_many([test_user, member_user])
    delegations_col.insert_many([delegation_1, delegation_2])
    docs_col.insert_many([doc_1, doc_2])
    assets_col.insert_many([asset_1, asset_2])
    
    token = generate_token(test_user)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    client = app.test_client()
    
    try:
        # --- TEST 1: Get list of documents (/document/list) ---
        print("\n--- Test 1: Fetching documents from /document/list ---")
        response1 = client.get("/document/list", headers=headers)
        print(f"Response status: {response1.status_code}")
        docs_list = json.loads(response1.data)
        print(f"Docs count: {len(docs_list)}")
        for d in docs_list:
            print(f"Doc: {d.get('title')}, Delegation ID: {d.get('delegation_id')}, Delegation Name: {d.get('delegation_name')}")
            
        assert response1.status_code == 200, "Expected status code 200"
        
        # Verify delegation_names are matched correctly
        d1_mapped = next(d for d in docs_list if d["doc_id"] == doc_1_id)
        d2_mapped = next(d for d in docs_list if d["doc_id"] == doc_2_id)
        
        assert d1_mapped["delegation_name"] == "Dinas Kebersihan", "Incorrect delegation mapping for Doc 1"
        assert d2_mapped["delegation_name"] == "Dinas Pekerjaan Umum", "Incorrect delegation mapping for Doc 2"
        print("Test 1 Passed!")

        # --- TEST 2: Get list of members (/auth/members) ---
        print("\n--- Test 2: Fetching members from /auth/members ---")
        response2 = client.get("/auth/members", headers=headers)
        print(f"Response status: {response2.status_code}")
        members_list = json.loads(response2.data)
        print(f"Members count: {len(members_list)}")
        for m in members_list:
            print(f"Member: {m.get('username')}, Delegation ID: {m.get('delegation_id')}, Delegation Name: {m.get('delegation_name')}")
            
        assert response2.status_code == 200, "Expected status code 200"
        
        member_mapped = next(m for m in members_list if m["username"] == "member_dinas_kebersihan")
        assert member_mapped["delegation_name"] == "Dinas Kebersihan", "Incorrect delegation mapping for member"
        print("Test 2 Passed!")

        # --- TEST 3: Get list of assets (/auth/assets) ---
        print("\n--- Test 3: Fetching assets from /auth/assets ---")
        response3 = client.get("/auth/assets", headers=headers)
        print(f"Response status: {response3.status_code}")
        assets_list = json.loads(response3.data)
        print(f"Assets count: {len(assets_list)}")
        for a in assets_list:
            print(f"Asset: {a.get('name')}, Delegation ID: {a.get('delegation_id')}, Delegation Name: {a.get('delegation_name')}")
            
        assert response3.status_code == 200, "Expected status code 200"
        
        a1_mapped = next(a for a in assets_list if str(a["id"]) == str(asset_1_id))
        a2_mapped = next(a for a in assets_list if str(a["id"]) == str(asset_2_id))
        
        assert a1_mapped["delegation_name"] == "Dinas Kebersihan", "Incorrect delegation mapping for Asset 1"
        assert a2_mapped["delegation_name"] == "Dinas Pekerjaan Umum", "Incorrect delegation mapping for Asset 2"
        print("Test 3 Passed!")
        
        # --- TEST 4: Semantic Search Visibility Check ---
        print("\n--- Test 4: Performing semantic search visibility check ---")
        member_token = generate_token(member_user)
        member_headers = {
            "Authorization": f"Bearer {member_token}",
            "Content-Type": "application/json"
        }
        
        response4 = client.post("/ai/semantic-search", headers=member_headers, data=json.dumps({"query": "sampah dan jalan"}))
        print(f"Response status: {response4.status_code}")
        results4 = json.loads(response4.data)
        print(f"Search results for member: {results4}")
        
        assert response4.status_code == 200
        found_doc_ids = [r["doc_id"] for r in results4]
        # member is only allowed to see doc_1, so doc_2 must not be returned
        assert doc_2_id not in found_doc_ids, "Restricted document 2 was returned to unauthorized member!"
        print("Test 4 Passed!")
        
        print("\n=== ALL TESTS PASSED SUCCESSFULLY ===")
        
    finally:
        # Cleanup
        print("\n--- Cleaning up test records ---")
        users_col.delete_many({"org_id": test_org_id})
        delegations_col.delete_many({"org_id": test_org_id})
        docs_col.delete_many({"org_id": test_org_id})
        assets_col.delete_many({"org_id": test_org_id})
        print("Cleanup completed.")

if __name__ == "__main__":
    run_test()

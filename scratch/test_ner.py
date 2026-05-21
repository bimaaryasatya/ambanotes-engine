import os
import sys
import jwt
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_gateway.api import app
from common.config import Config

# Generate a mock token for testing
user_payload = {
    "_id": "60d5ec4b9b1d8b15d8f6d7a1",
    "username": "tester",
    "role": "owner",
    "org_id": "org_123"
}
payload = {
    "user_id": str(user_payload["_id"]),
    "username": user_payload["username"],
    "role": user_payload["role"],
    "org_id": user_payload.get("org_id"),
    "exp": datetime.utcnow() + timedelta(hours=1)
}
token = jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm="HS256")
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

client = app.test_client()

# Sample text for testing extraction
test_text = (
    "Surat Undangan Resmi nomor 123/UND-DIR/V/2026. Kami dari PT Abadi Jaya mengundang "
    "Budi Santoso untuk hadir pada pertemuan tanggal 25 Mei 2026 di Jakarta."
)

def run_test():
    print("=== TESTING LOCAL MODE (DEFAULT CONFIG) ===")
    app.config['NER_DEFAULT_MODE'] = 'local'
    response = client.post(
        '/ner/extract',
        headers=headers,
        json={"text": test_text}
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response JSON: {response.get_json()}\n")

    print("=== TESTING MISTRAL MODE (EXPLICIT PARAMETER) ===")
    response = client.post(
        '/ner/extract',
        headers=headers,
        json={"text": test_text, "mode": "mistral"}
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response JSON: {response.get_json()}\n")

    print("=== TESTING DEFAULT CONFIG SWITCH TO MISTRAL ===")
    app.config['NER_DEFAULT_MODE'] = 'mistral'
    response = client.post(
        '/ner/extract',
        headers=headers,
        json={"text": test_text}  # No mode parameter
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response JSON: {response.get_json()}\n")

    print("=== TESTING MISTRAL FALLBACK ON FAILURE ===")
    # Temporarily corrupt API key to force Mistral to fail
    original_key = Config.MISTRAL_API_KEY
    Config.MISTRAL_API_KEY = "invalid_key"
    
    response = client.post(
        '/ner/extract',
        headers=headers,
        json={"text": test_text, "mode": "mistral"}
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response JSON: {response.get_json()}\n")
    
    # Restore key
    Config.MISTRAL_API_KEY = original_key

if __name__ == '__main__':
    run_test()

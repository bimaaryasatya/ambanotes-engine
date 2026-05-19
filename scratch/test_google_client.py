import os
import sys
import requests
import urllib.parse
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

client_id = os.getenv("GOOGLE_CLIENT_ID")
client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")

print("--- TESTING GOOGLE OAUTH CONFIGURATION ---")
print(f"GOOGLE_CLIENT_ID: {client_id}")
print(f"GOOGLE_CLIENT_SECRET: {'*' * len(client_secret) if client_secret else 'None'}")
print(f"GOOGLE_REDIRECT_URI: {redirect_uri}")

# URL encode parameters
encoded_redirect = urllib.parse.quote(redirect_uri) if redirect_uri else ""
encoded_scope = urllib.parse.quote("https://www.googleapis.com/auth/drive.file")

auth_url = (
    "https://accounts.google.com/o/oauth2/v2/auth?"
    "response_type=code&"
    f"client_id={client_id}&"
    f"redirect_uri={encoded_redirect}&"
    f"scope={encoded_scope}&"
    "access_type=offline&"
    "prompt=consent&"
    "state=test_user_id"
)

print("\n--- GENERATED OAUTH URL ---")
print(auth_url)

print("\n--- TESTING GOOGLE AUTHENTICATION SERVER RESPONSE ---")
try:
    # Send a request to Google Auth endpoint to see if they reject the client ID or redirect URI
    # Note: Google's auth endpoint is interactive, so we follow the redirect or check status.
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(auth_url, headers=headers, allow_redirects=True, timeout=10)
    print(f"HTTP Status: {res.status_code}")
    if "Error 400" in res.text or "invalid_request" in res.text or "request is invalid" in res.text.lower():
        print("[FAIL] Google OAuth page returned an error. Possible reasons:")
        print("  1. The GOOGLE_CLIENT_ID is not valid or doesn't exist.")
        print("  2. The GOOGLE_REDIRECT_URI is not configured in Google Cloud Console.")
    else:
        print("[SUCCESS] The OAuth URL was loaded successfully without initial Google API server errors!")
except Exception as e:
    print(f"Error calling Google Auth Server: {str(e)}")

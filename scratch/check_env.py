import os
from dotenv import load_dotenv

load_dotenv()

user = os.getenv("MAIL_USERNAME")
pw = os.getenv("MAIL_PASSWORD")

print(f"DEBUG ENV:")
print(f"MAIL_USERNAME: '{user}'")
if pw:
    print(f"MAIL_PASSWORD: '{pw[:2]}****{pw[-2:]}' (Length: {len(pw)})")
else:
    print("MAIL_PASSWORD: NOT FOUND")

if pw and " " in pw:
    print("WARNING: There is a SPACE in your password!")

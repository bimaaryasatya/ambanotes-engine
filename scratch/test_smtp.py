import smtplib
import os
from dotenv import load_dotenv

load_dotenv()

def test_gmail():
    server = "smtp.gmail.com"
    port = 587
    user = os.getenv("MAIL_USERNAME")
    pw = os.getenv("MAIL_PASSWORD")

    print(f"Testing connection to {server}:{port}...")
    try:
        smtp = smtplib.SMTP(server, port)
        smtp.set_debuglevel(1) # See the conversation with Google
        smtp.starttls()
        print("TLS started. Attempting login...")
        smtp.login(user, pw)
        print("SUCCESS! Login successful.")
        smtp.quit()
    except Exception as e:
        print(f"\nFAILED: {str(e)}")

if __name__ == "__main__":
    test_gmail()

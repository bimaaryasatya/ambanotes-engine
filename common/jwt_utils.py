import jwt
from datetime import datetime, timedelta
from common.config import Config

def generate_token(user):
    payload = {
        "user_id": str(user["_id"]),
        "role": user["role"],
        "org_id": user.get("org_id"),
        "exp": datetime.utcnow() + timedelta(days=1)
    }
    return jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm="HS256")

def verify_token(token):
    return jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"])
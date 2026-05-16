import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from common.config import Config


def generate_token(user):
    payload = {
        "user_id": str(user["_id"]),
        "username": user["username"],
        "role": user["role"],
        "org_id": user.get("org_id"),
        "exp": datetime.utcnow() + timedelta(hours=8)
    }
    return jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm="HS256")


def verify_token(token):
    return jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"])


def token_required(f):
    """
    Decorator untuk memproteksi endpoint dengan JWT.
    Meng-inject 'current_user' (dict payload JWT) sebagai parameter pertama fungsi.

    Cara pakai di endpoint:
        @blueprint.route('/path', methods=['POST'])
        @token_required
        def my_endpoint(current_user):
            org_id = current_user['org_id']
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        # Debug: log the auth header received
        print(f"[AUTH DEBUG] Authorization header: '{auth_header[:50]}...' (len={len(auth_header)})")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authorization header missing or invalid"}), 401

        token = auth_header.split(" ", 1)[1]
        try:
            payload = verify_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(payload, *args, **kwargs)
    return decorated


def role_required(*allowed_roles):
    """
    Decorator untuk membatasi akses endpoint berdasarkan role.
    Harus dipakai di bawah @token_required.

    Cara pakai:
        @blueprint.route('/path', methods=['DELETE'])
        @token_required
        @role_required('owner')
        def delete_something(current_user):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(current_user, *args, **kwargs):
            if current_user.get("role") not in allowed_roles:
                return jsonify({
                    "error": "Access forbidden: insufficient permissions",
                    "required_role": list(allowed_roles),
                    "your_role": current_user.get("role")
                }), 403
            return f(current_user, *args, **kwargs)
        return decorated
    return decorator
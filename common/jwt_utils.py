import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from common.config import Config
import secrets


def _get_jwt_secret():
    secret = Config.JWT_SECRET_KEY or ""
    if len(secret) < 32:
        raise ValueError(
            "JWT_SECRET_KEY must be at least 32 characters long for secure JWT signing"
        )
    return secret


def generate_token(user):
    now = datetime.utcnow()
    delegation_id = user.get("delegation_id")
    if delegation_id:
        delegation_id = str(delegation_id)
    payload = {
        "user_id": str(user["_id"]),
        "username": user["username"],
        "role": user["role"],
        "org_id": user.get("org_id"),
        "delegation_id": delegation_id,
        "iss": Config.JWT_ISSUER,
        "aud": Config.JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "jti": secrets.token_hex(16),
        "exp": now + timedelta(hours=Config.JWT_EXP_HOURS),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=Config.JWT_ALGORITHM)


def verify_token(token):
    return jwt.decode(
        token,
        _get_jwt_secret(),
        algorithms=[Config.JWT_ALGORITHM],
        issuer=Config.JWT_ISSUER,
        audience=Config.JWT_AUDIENCE,
        options={
            "require": ["exp", "iat", "nbf", "iss", "aud", "jti", "user_id"],
        },
    )


def generate_purpose_token(purpose, email, extra_payload=None):
    """
    Generates a short-lived JWT for a specific purpose (e.g., email verification, login verification).
    """
    now = datetime.utcnow()
    payload = {
        "purpose": purpose,
        "email": email,
        "iss": Config.JWT_ISSUER,
        "aud": Config.JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "jti": secrets.token_hex(16),
        "exp": now + timedelta(minutes=15),
    }
    if extra_payload:
        payload.update(extra_payload)
    return jwt.encode(payload, _get_jwt_secret(), algorithm=Config.JWT_ALGORITHM)


def verify_purpose_token(token, expected_purpose):
    """
    Verifies a purpose-limited JWT and returns the payload if valid.
    Raises jwt.InvalidTokenError if invalid.
    """
    payload = jwt.decode(
        token,
        _get_jwt_secret(),
        algorithms=[Config.JWT_ALGORITHM],
        issuer=Config.JWT_ISSUER,
        audience=Config.JWT_AUDIENCE,
        options={"require": ["exp", "iat", "nbf", "iss", "aud", "jti", "purpose", "email"]},
    )
    if payload.get("purpose") != expected_purpose:
        raise jwt.InvalidTokenError("Invalid token purpose")
    return payload


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
        token = None

        if auth_header:
            # Handle both "Bearer <token>" and raw "<token>"
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]
            else:
                token = auth_header
        else:
            # Fallback to cookies
            token = request.cookies.get("token")

        if not token:
            return jsonify({"error": "Authorization token is missing"}), 401
        try:
            payload = verify_token(token)
        except ValueError as e:
            from common.logger import log_event
            log_event("jwt_utils", f"JWT Secret Key configuration validation failed: {str(e)}", severity="error")
            return jsonify({"error": "Authentication system misconfigured"}), 500
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidAudienceError:
            return jsonify({"error": "Invalid token audience"}), 401
        except jwt.InvalidIssuerError:
            return jsonify({"error": "Invalid token issuer"}), 401
        except jwt.MissingRequiredClaimError as e:
            return jsonify({"error": f"Missing token claim: {e.claim}"}), 401
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
            role = current_user.get("role")
            if role == "admin" or role in allowed_roles:
                return f(current_user, *args, **kwargs)
            return jsonify({
                "error": "Access forbidden: insufficient permissions",
                "required_role": list(allowed_roles),
                "your_role": role
            }), 403
        return decorated
    return decorator

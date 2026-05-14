import os
import sys
import re

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
from common.db import users_col, orgs_col
from common.jwt_utils import generate_token
from common.logger import log_event
import uuid
import secrets
import datetime

auth_bp = Blueprint('auth', __name__)

# --- Helpers ---

def _validate_password(password: str) -> str | None:
    """Returns an error message if password is invalid, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters long"
    if not re.search(r"[A-Za-z]", password):
        return "Password must contain at least one letter"
    if not re.search(r"\d", password):
        return "Password must contain at least one number"
    return None

def _validate_username(username: str) -> str | None:
    """Returns an error message if username is invalid, else None."""
    if len(username) < 3 or len(username) > 30:
        return "Username must be between 3 and 30 characters"
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return "Username may only contain letters, numbers, and underscores"
    return None


# --- Endpoints ---

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    User Registration
    ---
    tags:
      - Auth
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - username
            - email
            - password
            - action
          properties:
            username:
              type: string
              example: "user123"
              description: "3-30 karakter, hanya huruf, angka, dan underscore"
            email:
              type: string
              example: "user@example.com"
            password:
              type: string
              example: "Password123"
              description: "Minimal 8 karakter, harus mengandung huruf dan angka"
            action:
              type: string
              enum: [create_org, join_org]
              example: "create_org"
            org_name:
              type: string
              description: Wajib jika action adalah create_org
              example: "My Organization"
            invitation_code:
              type: string
              description: Wajib jika action adalah join_org
              example: "ABCD1234"
    responses:
      201:
        description: User registered successfully
      400:
        description: Validation error or username/email already exists
    """
    data = request.json or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    action = data.get('action')

    # --- Input Validation ---
    if not username or not password or not action or not email:
        return jsonify({"error": "Missing required fields: username, email, password, action"}), 400

    username_err = _validate_username(username)
    if username_err:
        return jsonify({"error": username_err}), 400

    password_err = _validate_password(password)
    if password_err:
        return jsonify({"error": password_err}), 400

    if action not in ("create_org", "join_org"):
        return jsonify({"error": "action must be 'create_org' or 'join_org'"}), 400

    # --- Uniqueness Check ---
    if users_col.find_one({"username": username}):
        return jsonify({"error": "Username already exists"}), 400

    if users_col.find_one({"email": email}):
        return jsonify({"error": "Email already registered"}), 400

    role = "owner" if action == "create_org" else "member"
    org_id = None
    invitation_code = None

    if action == "create_org":
        org_name = data.get('org_name', '').strip()
        if not org_name:
            return jsonify({"error": "Organization name is required for create_org"}), 400

        invitation_code = secrets.token_hex(4).upper()
        org_result = orgs_col.insert_one({
            "name": org_name,
            "invitation_code": invitation_code,
            "created_at": datetime.datetime.utcnow()
        })
        org_id = str(org_result.inserted_id)
        log_event("auth_service", f"Org created: {org_name}")

    elif action == "join_org":
        invitation_code_input = data.get('invitation_code', '').strip()
        if not invitation_code_input:
            return jsonify({"error": "invitation_code is required for join_org"}), 400
        org = orgs_col.find_one({"invitation_code": invitation_code_input})
        if not org:
            return jsonify({"error": "Invalid invitation code"}), 400
        org_id = str(org['_id'])
        log_event("auth_service", f"User joining org: {org['name']}")

    hashed_password = generate_password_hash(password)
    users_col.insert_one({
        "username": username,
        "email": email,
        "password": hashed_password,
        "role": role,
        "org_id": org_id,
        "created_at": datetime.datetime.utcnow()
    })

    log_event("auth_service", f"User registered: {username}")
    return jsonify({
        "message": "User registered successfully",
        "org_id": org_id,
        "invitation_code": invitation_code if action == "create_org" else None
    }), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    User Login
    ---
    tags:
      - Auth
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - username
            - password
          properties:
            username:
              type: string
              example: "user123"
            password:
              type: string
              example: "Password123"
    responses:
      200:
        description: Login successful, returns JWT token
        schema:
          type: object
          properties:
            message:
              type: string
              example: Login successful
            token:
              type: string
              description: JWT token, gunakan sebagai 'Bearer <token>' di header Authorization
            user:
              type: object
              properties:
                username:
                  type: string
                role:
                  type: string
                org_id:
                  type: string
      401:
        description: Invalid credentials
    """
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = users_col.find_one({"username": username})

    # Generic message to prevent user enumeration attacks
    if not user or not check_password_hash(user['password'], password):
        log_event("auth_service", f"Failed login attempt for: {username}")
        return jsonify({"error": "Invalid username or password"}), 401

    token = generate_token(user)
    log_event("auth_service", f"User logged in: {username}")

    return jsonify({
        "message": "Login successful",
        "token": token,
        "user": {
            "username": user['username'],
            "role": user['role'],
            "org_id": str(user.get('org_id', ''))
        }
    }), 200


@auth_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health Check Endpoint (Auth)
    ---
    tags:
      - Auth
    responses:
      200:
        description: Service is healthy
    """
    return jsonify({"status": "healthy", "service": "auth_service"}), 200
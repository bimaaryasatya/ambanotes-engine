import os
import sys

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
from common.db import users_col, orgs_col
from common.jwt_utils import generate_token
from common.logger import log_event
import uuid
import secrets

auth_bp = Blueprint('auth', __name__)

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
            - password
            - action
          properties:
            username:
              type: string
              example: "user123"
            password:
              type: string
              example: "password123"
            action:
              type: string
              enum: [create_org, join_org]
              example: "create_org"
            org_name:
              type: string
              description: Required if action is create_org
              example: "My Organization"
            invitation_code:
              type: string
              description: Required if action is join_org
              example: "ABCD1234"
    responses:
      201:
        description: User registered successfully
      400:
        description: Missing fields or username exists
    """
    data = request.json
    username = data.get('username')
    password = data.get('password')
    action = data.get('action') # create_org or join_org
    role = "owner" if action == "create_org" else "member"

    if not username or not password or not action:
        return jsonify({"error": "Missing required fields"}), 400

    if users_col.find_one({"username": username}):
        return jsonify({"error": "Username already exists"}), 400

    org_id = None
    invitation_code = None
    
    if action == "create_org":
        org_name = data.get('org_name')
        if not org_name:
            return jsonify({"error": "Organization name is required"}), 400
        
        invitation_code = secrets.token_hex(4).upper()
        org_result = orgs_col.insert_one({
            "name": org_name,
            "invitation_code": invitation_code,
            "created_at": uuid.uuid4().hex
        })
        org_id = str(org_result.inserted_id)
        log_event("auth_service", f"Org created: {org_name} with code {invitation_code}")

    elif action == "join_org":
        invitation_code = data.get('invitation_code')
        org = orgs_col.find_one({"invitation_code": invitation_code})
        if not org:
            return jsonify({"error": "Invalid invitation code"}), 400
        org_id = str(org['_id'])
        log_event("auth_service", f"User joining org: {org['name']}")

    hashed_password = generate_password_hash(password)
    users_col.insert_one({
        "username": username,
        "password": hashed_password,
        "role": role,
        "org_id": org_id
    })

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
              example: "password123"
    responses:
      200:
        description: Login successful
      401:
        description: Invalid credentials
    """
    data = request.json
    username = data.get('username')
    password = data.get('password')

    user = users_col.find_one({"username": username})
    if not user or not check_password_hash(user['password'], password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = generate_token(user)
    log_event("auth_service", f"User logged in: {username}")
    
    return jsonify({
        "message": "Login successful",
        "token": token,
        "user": {
            "username": user['username'],
            "role": user['role'],
            "org_id": str(user['org_id'])
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
    log_event("auth_service", "Health check requested")
    return jsonify({"status": "healthy", "service": "auth_service"}), 200
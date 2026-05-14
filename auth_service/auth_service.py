import os
import sys
import re

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
from common.db import users_col, orgs_col, invitations_col, delegations_col, assets_col, docs_col
from common.jwt_utils import generate_token, token_required, role_required
from common.logger import log_event
from bson.objectid import ObjectId
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
    User Registration (Create/Join Organization)
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
            email:
              type: string
              example: "user@example.com"
            password:
              type: string
              example: "Password123"
            action:
              type: string
              enum: [create_org, join_org]
              example: "create_org"
            org_name:
              type: string
            invitation_code:
              type: string
            delegation_id:
              type: string
    responses:
      201:
        description: User registered successfully
    """
    data = request.json or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    action = data.get('action')
    delegation_id = data.get('delegation_id')

    # --- Input Validation ---
    if not username or not password or not action or not email:
        return jsonify({"error": "Missing required fields"}), 400

    u_error = _validate_username(username)
    if u_error: return jsonify({"error": u_error}), 400

    p_error = _validate_password(password)
    if p_error: return jsonify({"error": p_error}), 400

    if users_col.find_one({"username": username}):
        return jsonify({"error": "Username already exists"}), 400
    
    if users_col.find_one({"email": email}):
        return jsonify({"error": "Email already exists"}), 400

    org_id = None
    role = 'member'

    if action == 'create_org':
        org_name = data.get('org_name', '').strip()
        if not org_name:
            return jsonify({"error": "Organization name is required"}), 400
        
        org_result = orgs_col.insert_one({
            "name": org_name,
            "created_at": datetime.datetime.utcnow()
        })
        org_id = str(org_result.inserted_id)
        role = 'owner'
    
    elif action == 'join_org':
        invite = invitations_col.find_one({"email": email, "status": "pending"})
        if not invite:
            return jsonify({"error": "No pending invitation found"}), 400
        
        org_id = str(invite['org_id'])
        role = invite.get('role', 'member')
        invitations_col.update_one({"_id": invite["_id"]}, {"$set": {"status": "accepted", "accepted_at": datetime.datetime.utcnow()}})

    hashed_password = generate_password_hash(password)
    user = {
        "username": username,
        "email": email,
        "password": hashed_password,
        "org_id": org_id,
        "delegation_id": delegation_id,
        "role": role,
        "created_at": datetime.datetime.utcnow()
    }

    result = users_col.insert_one(user)
    user_id = str(result.inserted_id)

    log_event("auth_service", f"User registered: {username}", user_id=user_id, org_id=org_id)

    return jsonify({
        "message": "User registered successfully",
        "user": {"id": user_id, "username": username, "email": email, "role": role, "org_id": org_id, "delegation_id": delegation_id}
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
            - email
            - password
          properties:
            email:
              type: string
              example: "user@example.com"
            password:
              type: string
              example: "Password123"
    responses:
      200:
        description: Login successful, returns token
      401:
        description: Invalid credentials
    """
    data = request.json or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    user = users_col.find_one({"email": email})

    if not user or not check_password_hash(user['password'], password):
        return jsonify({"error": "Invalid email or password"}), 401

    token = generate_token(user)
    log_event("auth_service", f"User logged in: {user['username']}", user_id=str(user['_id']), org_id=user.get('org_id'))

    return jsonify({
        "token": token,
        "user": {
            "id": str(user['_id']),
            "username": user['username'],
            "email": user['email'],
            "role": user.get('role', 'member'),
            "org_id": user.get('org_id'),
            "delegation_id": user.get('delegation_id')
        }
    }), 200


@auth_bp.route('/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    """
    Get Current User Profile
    ---
    tags:
      - Auth
    security:
      - BearerAuth: []
    responses:
      200:
        description: User profile data
    """
    user_id = current_user.get('user_id')
    user = users_col.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        return jsonify({"error": "User not found"}), 404
        
    user_data = {
        "id": str(user['_id']),
        "username": user['username'],
        "email": user['email'],
        "role": user.get('role', 'member'),
        "org_id": user.get('org_id'),
        "delegation_id": user.get('delegation_id')
    }
    
    if user.get('delegation_id'):
        delegation = delegations_col.find_one({"_id": ObjectId(user['delegation_id'])})
        if delegation:
            user_data['delegation_name'] = delegation.get('name')

    return jsonify(user_data), 200


@auth_bp.route('/delegations', methods=['POST'])
@token_required
@role_required('owner')
def create_delegation(current_user):
    """
    Create New Delegation (Owner Only)
    ---
    tags:
      - Enterprise
    security:
      - BearerAuth: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - name
          properties:
            name:
              type: string
              example: "Dinas Sosial"
    responses:
      201:
        description: Delegation created
    """
    data = request.json or {}
    name = data.get('name', '').strip()
    org_id = current_user.get('org_id')

    if not name:
        return jsonify({"error": "Delegation name is required"}), 400

    delegation = {"name": name, "org_id": org_id, "created_at": datetime.datetime.utcnow()}
    result = delegations_col.insert_one(delegation)
    delegation['_id'] = str(result.inserted_id)
    delegation['created_at'] = delegation['created_at'].isoformat()

    return jsonify(delegation), 201


@auth_bp.route('/delegations', methods=['GET'])
@token_required
def list_delegations(current_user):
    """
    List All Delegations in Organization
    ---
    tags:
      - Enterprise
    security:
      - BearerAuth: []
    responses:
      200:
        description: List of delegations
    """
    org_id = current_user.get('org_id')
    delegations = list(delegations_col.find({"org_id": org_id}))
    for d in delegations:
        d['_id'] = str(d['_id'])
        d['created_at'] = d['created_at'].isoformat() if 'created_at' in d else None
    return jsonify(delegations), 200


@auth_bp.route('/change-delegation', methods=['POST'])
@token_required
@role_required('owner')
def change_delegation(current_user):
    """
    Transfer User to Another Delegation (Owner Only)
    ---
    tags:
      - Enterprise
    security:
      - BearerAuth: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - target_user_id
            - new_delegation_id
          properties:
            target_user_id:
              type: string
            new_delegation_id:
              type: string
    responses:
      200:
        description: Transfer successful
    """
    org_id = current_user.get('org_id')
    data = request.json or {}
    target_user_id = data.get('target_user_id')
    new_del_id = data.get('new_delegation_id')

    if not target_user_id or not new_del_id:
        return jsonify({"error": "Missing IDs"}), 400

    target_user = users_col.find_one({"_id": ObjectId(target_user_id), "org_id": org_id})
    new_delegation = delegations_col.find_one({"_id": ObjectId(new_del_id), "org_id": org_id})

    if not target_user or not new_delegation:
        return jsonify({"error": "Invalid target user or delegation"}), 404

    users_col.update_one({"_id": ObjectId(target_user_id)}, {"$set": {"delegation_id": new_del_id}})
    docs_col.update_many({"user_id": target_user_id}, {"$set": {"delegation_id": new_del_id}})

    return jsonify({"message": f"User {target_user['username']} moved to {new_delegation['name']}"}), 200


@auth_bp.route('/assets', methods=['POST'])
@token_required
@role_required('owner')
def upload_asset(current_user):
    """
    Upload Letterhead or Signature (Owner Only)
    ---
    tags:
      - Enterprise
    security:
      - BearerAuth: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - type
            - delegation_id
            - image_data
          properties:
            type:
              type: string
              enum: [kop, ttd]
            delegation_id:
              type: string
            image_data:
              type: string
              description: Base64 image string
    responses:
      201:
        description: Asset uploaded
    """
    data = request.json or {}
    asset_type = data.get('type')
    delegation_id = data.get('delegation_id')
    image_data = data.get('image_data') 
    org_id = current_user.get('org_id')

    assets_col.update_one(
        {"type": asset_type, "delegation_id": delegation_id},
        {"$set": {"type": asset_type, "delegation_id": delegation_id, "org_id": org_id, "image_data": image_data, "updated_at": datetime.datetime.utcnow()}},
        upsert=True
    )
    return jsonify({"message": f"Asset {asset_type} uploaded successfully"}), 201


@auth_bp.route('/invite', methods=['POST'])
@token_required
@role_required('owner')
def invite_member(current_user):
    """
    Invite New Member (Owner Only)
    ---
    tags:
      - Auth
    security:
      - BearerAuth: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - email
          properties:
            email:
              type: string
            role:
              type: string
    responses:
      201:
        description: Invitation sent
    """
    data = request.json or {}
    email = data.get('email', '').strip().lower()
    role = data.get('role', 'member')
    org_id = current_user.get('org_id')

    if not email:
        return jsonify({"error": "Email is required"}), 400
    
    invitations_col.insert_one({"email": email, "org_id": org_id, "role": role, "status": "pending", "created_at": datetime.datetime.utcnow()})
    return jsonify({"message": "Invitation sent successfully"}), 201


@auth_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "auth_service"}), 200
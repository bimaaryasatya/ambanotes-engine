import os
import sys
import re

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
from common.db import users_col, orgs_col, invitations_col
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
        log_event("auth_service", f"Org created: {org_name}", org_id=org_id, action="ORG_CREATED", metadata={"org_name": org_name})

    elif action == "join_org":
        invitation_code_input = data.get('invitation_code', '').strip()
        if not invitation_code_input:
            return jsonify({"error": "invitation_code is required for join_org"}), 400
        org = orgs_col.find_one({"invitation_code": invitation_code_input})
        if not org:
            return jsonify({"error": "Invalid invitation code"}), 400
        org_id = str(org['_id'])
        log_event("auth_service", f"User joining org via code: {org['name']}", org_id=org_id, action="JOIN_ORG_CODE")

    hashed_password = generate_password_hash(password)
    result = users_col.insert_one({
        "username": username,
        "email": email,
        "password": hashed_password,
        "role": role,
        "org_id": org_id,
        "created_at": datetime.datetime.utcnow()
    })

    user_id = str(result.inserted_id)
    log_event("auth_service", f"User registered: {username}", user_id=user_id, org_id=org_id, action="USER_REGISTERED")
    
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
        log_event("auth_service", f"Failed login attempt for: {username}", action="LOGIN_FAILED", metadata={"username": username})
        return jsonify({"error": "Invalid username or password"}), 401

    token = generate_token(user)
    log_event("auth_service", f"User logged in: {username}", user_id=str(user['_id']), org_id=user.get('org_id'), action="LOGIN_SUCCESS")

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


@auth_bp.route('/members/<user_id>', methods=['DELETE'])
@token_required
@role_required('admin')
def delete_member(current_user, user_id):
    """
    Delete Member by ID (Admin only)
    ---
    tags:
      - Auth
    security:
      - BearerAuth: []
    parameters:
      - name: user_id
        in: path
        type: string
        required: true
        description: The unique MongoDB user ID (_id) to delete
    responses:
      200:
        description: Member deleted successfully
        schema:
          type: object
          properties:
            message:
              type: string
              example: Member user123 deleted successfully
      400:
        description: Invalid ID format or self-deletion attempt
      401:
        description: Unauthorized
      403:
        description: Forbidden - admin role required or organization mismatch
      404:
        description: Member not found
    """
    log_event("auth_service", f"Delete request for user_id: {user_id} by admin: {current_user.get('username')}", 
              user_id=current_user.get("user_id"), org_id=current_user.get("org_id"), action="MEMBER_DELETE_REQUEST")

    try:
        obj_id = ObjectId(user_id)
    except Exception:
        return jsonify({"error": "Invalid user ID format"}), 400

    # Prevent self-deletion
    if user_id == current_user.get("user_id"):
        return jsonify({"error": "You cannot delete your own account via this endpoint"}), 400

    # Find the target user
    target_user = users_col.find_one({"_id": obj_id})

    if not target_user:
        return jsonify({"error": "User not found"}), 404

    # Ensure they belong to the same organization
    if str(target_user.get("org_id")) != str(current_user.get("org_id")):
        log_event("auth_service", f"Forbidden delete attempt: Admin {current_user.get('username')} tried to delete user {target_user.get('username')} from different org",
                  user_id=current_user.get("user_id"), org_id=current_user.get("org_id"), action="MEMBER_DELETE_FORBIDDEN")
        return jsonify({"error": "Access forbidden: user belongs to a different organization"}), 403

    result = users_col.delete_one({"_id": obj_id})

    if result.deleted_count:
        log_event("auth_service", f"User deleted: {target_user.get('username')} (ID: {user_id})",
                  user_id=current_user.get("user_id"), org_id=current_user.get("org_id"), action="MEMBER_DELETE_SUCCESS",
                  metadata={"target_user": target_user.get('username'), "target_id": user_id})
        return jsonify({"message": f"Member {target_user.get('username')} deleted successfully"}), 200

    return jsonify({"error": "Failed to delete member"}), 500


@auth_bp.route('/invite', methods=['POST'])
@token_required
@role_required('owner')
def invite_member(current_user):
    """
    Invite Member to Organization (Owner only)
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
              example: "newmember@example.com"
            role:
              type: string
              enum: [member, admin]
              default: member
              example: "member"
    responses:
      201:
        description: Invitation sent successfully
      400:
        description: Email already in organization or already invited
      401:
        description: Unauthorized
      403:
        description: Forbidden - owner role required
    """
    data = request.json or {}
    email = data.get('email', '').strip().lower()
    role = data.get('role', 'member')
    org_id = current_user.get('org_id')

    if not email:
        return jsonify({"error": "Email is required"}), 400
    
    if role not in ('member', 'admin'):
        return jsonify({"error": "Role must be 'member' or 'admin'"}), 400

    # Check if user already exists in THIS organization
    existing_user = users_col.find_one({"email": email, "org_id": org_id})
    if existing_user:
        return jsonify({"error": "User is already a member of your organization"}), 400

    # Check for existing pending invitation
    existing_invite = invitations_col.find_one({"email": email, "org_id": org_id, "status": "pending"})
    if existing_invite:
        return jsonify({"error": "An invitation is already pending for this email"}), 400

    # Get org name
    try:
        org = orgs_col.find_one({"_id": ObjectId(org_id)})
        org_name = org.get('name', 'Unknown Organization') if org else 'Unknown Organization'
    except Exception:
        org_name = "Unknown Organization"

    invitation = {
        "email": email,
        "org_id": org_id,
        "org_name": org_name,
        "invited_by": current_user.get('username'),
        "role": role,
        "status": "pending",
        "created_at": datetime.datetime.utcnow()
    }

    inv_result = invitations_col.insert_one(invitation)
    log_event("auth_service", f"Invitation sent to {email} by {current_user.get('username')}",
              user_id=current_user.get("user_id"), org_id=org_id, action="INVITE_SENT", 
              metadata={"invited_email": email, "invitation_id": str(inv_result.inserted_id)})

    return jsonify({"message": f"Invitation sent successfully to {email}"}), 201


@auth_bp.route('/invitations', methods=['GET'])
@token_required
def list_invitations(current_user):
    """
    List Pending Invitations for Current User
    ---
    tags:
      - Auth
    security:
      - BearerAuth: []
    responses:
      200:
        description: List of pending invitations
    """
    email = None
    user = users_col.find_one({"_id": ObjectId(current_user.get('user_id'))})
    if user:
        email = user.get('email')
    
    if not email:
        return jsonify([]), 200

    invites = list(invitations_col.find({"email": email.lower(), "status": "pending"}))
    for invite in invites:
        invite['_id'] = str(invite['_id'])
        invite['created_at'] = invite['created_at'].isoformat()
    
    return jsonify(invites), 200


@auth_bp.route('/invitations/<invitation_id>/accept', methods=['POST'])
@token_required
def accept_invitation(current_user, invitation_id):
    """
    Accept Invitation
    ---
    tags:
      - Auth
    security:
      - BearerAuth: []
    parameters:
      - name: invitation_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Invitation accepted successfully
      403:
        description: Invitation does not belong to you
      404:
        description: Invitation not found or no longer pending
    """
    try:
        invite_oid = ObjectId(invitation_id)
    except Exception:
        return jsonify({"error": "Invalid invitation ID"}), 400

    invite = invitations_col.find_one({"_id": invite_oid, "status": "pending"})
    if not invite:
        return jsonify({"error": "Invitation not found or already processed"}), 404

    user = users_col.find_one({"_id": ObjectId(current_user.get('user_id'))})
    if not user or user.get('email').lower() != invite.get('email').lower():
        return jsonify({"error": "This invitation was not sent to your email address"}), 403

    users_col.update_one(
        {"_id": user['_id']},
        {"$set": {
            "org_id": invite['org_id'],
            "role": invite['role']
        }}
    )

    invitations_col.update_one({"_id": invite_oid}, {"$set": {"status": "accepted", "processed_at": datetime.datetime.utcnow()}})
    
    log_event("auth_service", f"User {user['username']} accepted invitation to org {invite['org_name']}",
              user_id=str(user['_id']), org_id=invite['org_id'], action="INVITE_ACCEPTED",
              metadata={"org_name": invite['org_name']})
    
    return jsonify({"message": f"Successfully joined {invite['org_name']} as {invite['role']}"}), 200


@auth_bp.route('/invitations/<invitation_id>/reject', methods=['POST'])
@token_required
def reject_invitation(current_user, invitation_id):
    """
    Reject Invitation
    ---
    tags:
      - Auth
    security:
      - BearerAuth: []
    parameters:
      - name: invitation_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Invitation rejected successfully
    """
    try:
        invite_oid = ObjectId(invitation_id)
    except Exception:
        return jsonify({"error": "Invalid invitation ID"}), 400

    user = users_col.find_one({"_id": ObjectId(current_user.get('user_id'))})
    if not user:
        return jsonify({"error": "User not found"}), 404

    invite = invitations_col.find_one({"_id": invite_oid, "email": user.get('email').lower()})
    
    if not invite:
        return jsonify({"error": "Invitation not found"}), 404

    invitations_col.update_one({"_id": invite_oid}, {"$set": {"status": "rejected", "processed_at": datetime.datetime.utcnow()}})
    
    log_event("auth_service", f"User {user['username']} rejected invitation to org {invite.get('org_name')}",
              user_id=str(user['_id']), action="INVITE_REJECTED", metadata={"org_id": invite.get('org_id')})
    
    return jsonify({"message": "Invitation rejected"}), 200
import os
import sys
import re
import requests

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
from common.db import users_col, orgs_col, invitations_col, delegations_col, assets_col, docs_col, otps_col, logs_col, reminders_col, chats_col
from common.jwt_utils import generate_token, generate_purpose_token, verify_purpose_token, token_required, role_required
from common.email_utils import send_otp_email, send_invitation_email
from common.logger import log_event
from common.config import Config
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
    """Returns an error message if username/full name is invalid, else None."""
    if len(username) < 3 or len(username) > 50:
        return "Nama lengkap harus antara 3 dan 50 karakter"
    if not re.match(r"^[a-zA-Z0-9_ ]+$", username):
        return "Nama lengkap hanya boleh mengandung huruf, angka, spasi, dan garis bawah"
    return None


def _validate_org_name(name: str) -> str | None:
    if len(name) < 3 or len(name) > 100:
        return "Nama organisasi harus antara 3 dan 100 karakter"
    return None


def _find_org_by_id(org_id):
    if not org_id:
        return None
    try:
        return orgs_col.find_one({"_id": ObjectId(org_id) if isinstance(org_id, str) else org_id})
    except Exception:
        return None


# --- Endpoints ---

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    User Registration (Create/Join Organization)
    tags:
      - Auth
    consumes:
      - application/json
    produces:
      - application/json
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
    data = request.get_json(force=True, silent=True) or {}
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
    
    existing_user = users_col.find_one({"email": email})
    if existing_user:
        if existing_user.get('email_verified', False):
            return jsonify({"error": "Email already exists"}), 400
        # Unverified user re-registering → resume verification flow
        existing_user_id = str(existing_user['_id'])
        existing_username = existing_user.get('username', username)
        otp_code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
        expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
        otps_col.update_one(
            {"email": email, "purpose": "verify_email"},
            {"$set": {"otp": otp_code, "expiry": expiry, "purpose": "verify_email", "created_at": datetime.datetime.utcnow()}},
            upsert=True
        )
        send_otp_email(email, otp_code, purpose="verify_email")
        registration_token = generate_purpose_token(
            "verify_email",
            email,
            extra_payload={"user_id": existing_user_id, "username": existing_username}
        )
        otps_col.update_one(
            {"email": email, "purpose": "verify_email_token"},
            {"$set": {"token": registration_token, "expiry": expiry, "created_at": datetime.datetime.utcnow()}},
            upsert=True
        )
        return jsonify({
            "message": "Email already registered but not verified. OTP resent.",
            "requires_verification": True,
            "registration_token": registration_token,
            "email": email,
        }), 200

    org_id = None
    role = 'member'

    if action == 'create_org':
        org_name = data.get('org_name', '').strip()
        if not org_name:
            return jsonify({"error": "Organization name is required"}), 400
        
        import random
        import string
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not orgs_col.find_one({"invite_code": code}):
                invite_code = code
                break

        org_result = orgs_col.insert_one({
            "name": org_name,
            "invite_code": invite_code,
            "created_at": datetime.datetime.utcnow()
        })
        org_id = str(org_result.inserted_id)
        role = 'owner'
    
    elif action == 'join_org':
        invitation_code = data.get('invitation_code')
        if invitation_code:
            org = orgs_col.find_one({"invite_code": invitation_code.strip().upper()})
            if not org:
                try:
                    org = orgs_col.find_one({"_id": ObjectId(invitation_code.strip())})
                except Exception:
                    org = None
            if not org:
                return jsonify({"error": "Invalid invite code"}), 400
            
            org_id = str(org['_id'])
            role = 'member'
        else:
            invite = invitations_col.find_one({"email": email, "status": "pending"})
            if not invite:
                return jsonify({"error": "No pending invitation found or invite code not provided"}), 400
            
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
        "email_verified": False,
        "known_devices": [],
        "created_at": datetime.datetime.utcnow()
    }

    result = users_col.insert_one(user)
    user_id = str(result.inserted_id)

    # Generate and send OTP for email verification
    otp_code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
    otps_col.update_one(
        {"email": email, "purpose": "verify_email"},
        {"$set": {"otp": otp_code, "expiry": expiry, "purpose": "verify_email", "created_at": datetime.datetime.utcnow()}},
        upsert=True
    )

    email_success, email_msg = send_otp_email(email, otp_code, purpose="verify_email")
    if not email_success:
        log_event("auth_service", f"Failed to send verification email to {email}: {email_msg}", action="VERIFY_EMAIL_FAILED")

    # Generate short-lived registration token
    registration_token = generate_purpose_token(
        "verify_email",
        email,
        extra_payload={"user_id": user_id, "username": username}
    )

    log_event(
        "auth_service",
        f"User registered: {username} (email verification pending)",
        user_id=user_id,
        org_id=org_id,
        action="REGISTER_SUCCESS",
        audience="user" if role != "owner" else "owner",
        visibility="app",
        severity="info",
    )

    return jsonify({
        "message": "Registration successful. Please verify your email.",
        "requires_verification": True,
        "registration_token": registration_token,
        "email": email,
    }), 201


@auth_bp.route('/verify-email', methods=['POST'])
def verify_email():
    """
    Verify email using OTP sent after registration.
    ---
    tags:
      - Auth
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - registration_token
            - otp
          properties:
            registration_token:
              type: string
            otp:
              type: string
    responses:
      200:
        description: Email verified successfully
      400:
        description: Invalid or expired OTP
    """
    data = request.get_json(force=True, silent=True) or {}
    token = data.get('registration_token', '').strip()
    otp_input = data.get('otp', '').strip()

    if not token or not otp_input:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        payload = verify_purpose_token(token, "verify_email")
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Registration token has expired. Please register again."}), 400
    except Exception:
        return jsonify({"error": "Invalid registration token"}), 400

    email = payload.get('email')

    otp_record = otps_col.find_one({"email": email, "purpose": "verify_email"})
    if not otp_record:
        return jsonify({"error": "No OTP found. Please request a new one."}), 400

    if otp_record['otp'] != otp_input:
        return jsonify({"error": "Invalid OTP code"}), 400

    if datetime.datetime.utcnow() > otp_record['expiry']:
        return jsonify({"error": "OTP has expired"}), 400

    # Mark email as verified
    users_col.update_one({"email": email}, {"$set": {"email_verified": True}})
    otps_col.delete_one({"email": email, "purpose": "verify_email"})
    otps_col.delete_one({"email": email, "purpose": "verify_email_token"})

    log_event("auth_service", f"Email verified: {email}", action="EMAIL_VERIFIED")

    return jsonify({"message": "Email verified successfully. You can now log in."}), 200


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    User Login
    ---
    tags:
      - Auth
    consumes:
      - application/json
    produces:
      - application/json
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
    data = request.get_json(force=True, silent=True) or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    device_id = data.get('device_id', '').strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = users_col.find_one({"email": email})

    if not user or not check_password_hash(user['password'], password):
        log_event("auth_service", f"Failed login attempt for email: {email}", action="LOGIN_FAILED")
        return jsonify({"error": "Invalid email or password"}), 401

    # Check if email is verified
    if not user.get('email_verified', False):
        # Send a fresh OTP and return a registration_token-like response
        otp_code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
        expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
        otps_col.update_one(
            {"email": email, "purpose": "verify_email"},
            {"$set": {"otp": otp_code, "expiry": expiry, "purpose": "verify_email", "created_at": datetime.datetime.utcnow()}},
            upsert=True
        )
        send_otp_email(email, otp_code, purpose="verify_email")
        registration_token = generate_purpose_token(
            "verify_email",
            email,
            extra_payload={"user_id": str(user['_id']), "username": user['username']}
        )
        return jsonify({
            "error": "Email not verified. Please verify your email first.",
            "requires_verification": True,
            "registration_token": registration_token,
            "email": email,
        }), 403

    known_devices = user.get('known_devices', [])
    is_known_device = device_id and device_id in known_devices

    if not is_known_device:
        # Reuse existing pending OTP if still valid
        existing_otp = otps_col.find_one({"email": email, "purpose": "verify_login"})
        if existing_otp and existing_otp.get('expiry') and existing_otp['expiry'] > datetime.datetime.utcnow():
            existing_token = otps_col.find_one({"email": email, "purpose": "verify_login_token"})
            if existing_token:
                return jsonify({
                    "requires_otp": True,
                    "login_token": existing_token['token'],
                    "email": email,
                    "message": "Masukkan kode OTP yang sudah dikirim ke email Anda."
                }), 200

        # Send new OTP for new device verification
        otp_code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
        expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
        otps_col.update_one(
            {"email": email, "purpose": "verify_login"},
            {"$set": {"otp": otp_code, "expiry": expiry, "purpose": "verify_login", "device_id": device_id, "created_at": datetime.datetime.utcnow()}},
            upsert=True
        )
        send_otp_email(email, otp_code, purpose="verify_login")

        login_token = generate_purpose_token(
            "verify_login",
            email,
            extra_payload={"user_id": str(user['_id']), "device_id": device_id}
        )
        # Store login_token for reuse on page reload
        otps_col.update_one(
            {"email": email, "purpose": "verify_login_token"},
            {"$set": {"token": login_token, "expiry": expiry, "created_at": datetime.datetime.utcnow()}},
            upsert=True
        )
        return jsonify({
            "requires_otp": True,
            "login_token": login_token,
            "email": email,
            "message": "New device detected. Please check your email for OTP."
        }), 200

    token = generate_token(user)
    log_event(
        "auth_service",
        f"User logged in: {user['username']}",
        user_id=str(user['_id']),
        org_id=user.get('org_id'),
        action="LOGIN_SUCCESS",
        audience="owner" if user.get('role') == 'owner' else "user",
        visibility="app",
        severity="info",
    )
    role = user.get('role', 'member')
    redirect_map = {"owner": "/dashboard", "developer": "/console", "superadmin": "/developers", "member": "/dashboard"}
    response = jsonify({
        "token": token,
        "redirect": redirect_map.get(role, "/dashboard"),
        "user": {
            "id": str(user['_id']),
            "username": user['username'],
            "email": user['email'],
            "role": role,
            "org_id": user.get('org_id'),
            "delegation_id": user.get('delegation_id')
        }
    })
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        samesite="Lax",
        max_age=Config.JWT_EXP_HOURS * 3600,
        path="/"
    )
    return response, 200


@auth_bp.route('/verify-login', methods=['POST'])
def verify_login():
    """
    Verify new device login using OTP.
    ---
    tags:
      - Auth
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - login_token
            - otp
          properties:
            login_token:
              type: string
            otp:
              type: string
    responses:
      200:
        description: Device verified and logged in
      400:
        description: Invalid or expired OTP
    """
    data = request.get_json(force=True, silent=True) or {}
    token = data.get('login_token', '').strip()
    otp_input = data.get('otp', '').strip()

    if not token or not otp_input:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        payload = verify_purpose_token(token, "verify_login")
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Login token has expired. Please login again."}), 400
    except Exception:
        return jsonify({"error": "Invalid login token"}), 400

    email = payload.get('email')
    device_id = payload.get('device_id', '')

    otp_record = otps_col.find_one({"email": email, "purpose": "verify_login"})
    if not otp_record:
        return jsonify({"error": "No OTP found. Please login again."}), 400

    if otp_record['otp'] != otp_input:
        return jsonify({"error": "Invalid OTP code"}), 400

    if datetime.datetime.utcnow() > otp_record['expiry']:
        return jsonify({"error": "OTP has expired"}), 400

    # Add device to known devices
    if device_id:
        users_col.update_one(
            {"email": email},
            {"$addToSet": {"known_devices": device_id}}
        )

    # Delete used OTP and token
    otps_col.delete_one({"email": email, "purpose": "verify_login"})
    otps_col.delete_one({"email": email, "purpose": "verify_login_token"})

    # Generate full auth token
    user = users_col.find_one({"email": email})
    if not user:
        return jsonify({"error": "User not found"}), 404

    auth_token = generate_token(user)
    role = user.get('role', 'member')
    redirect_map = {"owner": "/dashboard", "developer": "/console", "superadmin": "/developers", "member": "/dashboard"}

    log_event(
        "auth_service",
        f"User logged in from new device: {user['username']}",
        user_id=str(user['_id']),
        org_id=user.get('org_id'),
        action="LOGIN_NEW_DEVICE",
        audience="owner" if role == 'owner' else "user",
        visibility="app",
        severity="info",
    )

    response = jsonify({
        "token": auth_token,
        "redirect": redirect_map.get(role, "/dashboard"),
        "user": {
            "id": str(user['_id']),
            "username": user['username'],
            "email": user['email'],
            "role": role,
            "org_id": user.get('org_id'),
            "delegation_id": user.get('delegation_id')
        }
    })
    response.set_cookie(
        key="token",
        value=auth_token,
        httponly=True,
        samesite="Lax",
        max_age=Config.JWT_EXP_HOURS * 3600,
        path="/"
    )
    return response, 200


@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    """
    Resend OTP for email verification or login verification.
    ---
    tags:
      - Auth
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - email
            - purpose
          properties:
            email:
              type: string
            purpose:
              type: string
              enum: [verify_email, verify_login]
    responses:
      200:
        description: OTP resent
    """
    data = request.get_json(force=True, silent=True) or {}
    email = data.get('email', '').strip().lower()
    purpose = data.get('purpose', '').strip()

    if not email or not purpose:
        return jsonify({"error": "Missing required fields"}), 400

    if purpose not in ("verify_email", "verify_login"):
        return jsonify({"error": "Invalid purpose"}), 400

    # Check OTP record exists with the given purpose
    existing = otps_col.find_one({"email": email, "purpose": purpose})
    if not existing:
        return jsonify({"error": "No pending verification found for this email"}), 400

    # Generate new OTP
    otp_code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)

    otps_col.update_one(
        {"email": email, "purpose": purpose},
        {"$set": {"otp": otp_code, "expiry": expiry, "created_at": datetime.datetime.utcnow()}}
    )

    send_otp_email(email, otp_code, purpose=purpose)

    log_event("auth_service", f"OTP resent to {email} for {purpose}", action="OTP_RESENT")

    return jsonify({"message": "OTP has been resent to your email"}), 200


@auth_bp.route('/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    """
    Get Current User Profile
    ---
    tags:
      - Auth
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
    responses:
      200:
        description: User profile data
      401:
        description: Unauthorized
    """
    user_id = current_user.get('user_id')
    try:
        user = users_col.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return jsonify({"error": "Invalid user ID in token"}), 400
    
    if not user:
        return jsonify({"error": "User not found"}), 404
        
    user_data = {
        "id": str(user['_id']),
        "username": user['username'],
        "email": user['email'],
        "role": user.get('role', 'member'),
        "org_id": user.get('org_id'),
        "delegation_id": user.get('delegation_id'),
        "google_drive_connected": user.get('google_drive_connected', False),
        "profile_image_data": user.get('profile_image_data'),
    }
    
    if user.get('org_id'):
        try:
            org = orgs_col.find_one({"_id": ObjectId(user['org_id'])})
            if org:
                user_data['org_name'] = org.get('name') or "Personal Workspace"
                invite_code = org.get('invite_code')
                if not invite_code:
                    import random
                    import string
                    while True:
                        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                        if not orgs_col.find_one({"invite_code": code}):
                            invite_code = code
                            break
                    orgs_col.update_one({"_id": org["_id"]}, {"$set": {"invite_code": invite_code}})
                user_data['invite_code'] = invite_code
        except Exception as e:
            print(f"Error fetching org invite code: {e}")
    else:
        user_data['org_name'] = "Personal Workspace"
    
    if user.get('delegation_id'):
        try:
            delegation = delegations_col.find_one({"_id": ObjectId(user['delegation_id'])})
            if delegation:
                user_data['delegation_name'] = delegation.get('name')
        except Exception:
            # If delegation_id is invalid (like the word 'string'), just ignore it
            user_data['delegation_name'] = "Invalid Delegation ID"

    return jsonify(user_data), 200


@auth_bp.route('/profile', methods=['PUT'])
@token_required
def update_profile(current_user):
    """
    Update Current User Profile
    ---
    tags:
      - Auth
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            username:
              type: string
            profile_image_data:
              type: string
            org_name:
              type: string
    responses:
      200:
        description: Profile updated successfully
    """
    user_id = current_user.get('user_id')
    data = request.get_json(force=True, silent=True) or {}

    try:
        user = users_col.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return jsonify({"error": "Invalid user ID in token"}), 400

    if not user:
        return jsonify({"error": "User not found"}), 404

    update_fields = {}
    username = (data.get('username') or '').strip()
    profile_image_data = data.get('profile_image_data')
    org_name = (data.get('org_name') or '').strip()

    if username:
        u_error = _validate_username(username)
        if u_error:
            return jsonify({"error": u_error}), 400

        existing_user = users_col.find_one({
            "username": username,
            "_id": {"$ne": user["_id"]},
        })
        if existing_user:
            return jsonify({"error": "Username already exists"}), 400
        update_fields["username"] = username

    if profile_image_data is not None:
        update_fields["profile_image_data"] = profile_image_data

    if update_fields:
        users_col.update_one({"_id": user["_id"]}, {"$set": update_fields})

    if org_name:
        if current_user.get('role') not in ('owner', 'admin'):
            return jsonify({"error": "Only organization owner can rename the organization"}), 403
        if len(org_name) < 3 or len(org_name) > 80:
            return jsonify({"error": "Organization name must be between 3 and 80 characters"}), 400
        if not user.get('org_id'):
            return jsonify({"error": "Organization not found for current user"}), 404
        orgs_col.update_one(
            {"_id": ObjectId(user['org_id'])},
            {"$set": {"name": org_name}}
        )

    updated_user = users_col.find_one({"_id": user["_id"]}) or user
    updated_org_name = None
    if updated_user.get('org_id'):
        org = orgs_col.find_one({"_id": ObjectId(updated_user['org_id'])})
        if org:
            updated_org_name = org.get('name')

    log_event(
        "auth_service",
        f"Profile updated for user: {updated_user.get('username', user_id)}",
        user_id=user_id,
        org_id=current_user.get('org_id'),
        action="PROFILE_UPDATE",
        audience="owner" if updated_user.get("role") == "owner" else "user",
        visibility="app",
        severity="info",
    )

    return jsonify({
        "message": "Profile updated successfully",
        "user": {
            "id": str(updated_user["_id"]),
            "username": updated_user.get("username", ""),
            "email": updated_user.get("email", ""),
            "role": updated_user.get("role", "member"),
            "org_id": updated_user.get("org_id"),
            "org_name": updated_org_name,
            "profile_image_data": updated_user.get("profile_image_data"),
        }
    }), 200


@auth_bp.route('/activity-logs', methods=['GET'])
@token_required
def get_activity_logs(current_user):
    """
    Get Current User Activity Logs
    ---
    tags:
      - Auth
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
      - name: limit
        in: query
        type: integer
        required: false
        description: Maximum number of activity logs to return
    responses:
      200:
        description: User activity logs
    """
    user_id = current_user.get('user_id')
    org_id = current_user.get('org_id')
    role = current_user.get('role')
    limit = request.args.get('limit', default=50, type=int) or 50
    limit = max(1, min(limit, 200))

    try:
        query = {
            "audience": {
                "$in": ["user", "owner"]
            },
            "visibility": "app",
        }

        if role == 'owner' and org_id:
            query["org_id"] = org_id
        else:
            query["user_id"] = user_id

        logs = list(
            logs_col.find(query)
            .sort("timestamp", -1)
            .limit(limit)
        )

        result = []
        for item in logs:
            result.append({
                "id": str(item.get("_id")),
                "service": item.get("service"),
                "message": item.get("message"),
                "action": item.get("action"),
                "metadata": item.get("metadata", {}),
                "timestamp": item.get("timestamp").isoformat() if item.get("timestamp") else None,
            })
        return jsonify(result), 200
    except Exception as e:
        log_event(
            "auth_service",
            f"Failed to fetch activity logs for user: {user_id}",
            user_id=user_id,
            org_id=current_user.get('org_id'),
            action="ACTIVITY_LOGS_FETCH_FAILED",
            metadata={"error": str(e)},
            audience="developer",
            visibility="internal",
            severity="error",
        )
        return jsonify({"error": "Failed to fetch activity logs"}), 500


@auth_bp.route('/organization', methods=['GET'])
@token_required
def get_organization(current_user):
    """
    Get Organization Details
    """
    org_id = current_user.get('org_id')
    if not org_id:
        return jsonify({"error": "Organization not found"}), 404
    try:
        org = orgs_col.find_one({"_id": ObjectId(org_id)})
        if not org:
            return jsonify({"error": "Organization not found"}), 404
        return jsonify({
            "id": str(org['_id']),
            "name": org.get('name'),
            "invite_code": org.get('invite_code')
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@auth_bp.route('/organization', methods=['PUT'])
@token_required
@role_required('owner')
def update_organization(current_user):
    """
    Update Organization Name (Owner Only)
    ---
    tags:
      - Enterprise
    security:
      - BearerAuth: []
    """
    org_id = current_user.get('org_id')
    data = request.get_json(force=True, silent=True) or {}
    name = data.get('name', '').strip()

    if not org_id:
        return jsonify({"error": "Organization not found"}), 404
    if not name:
        return jsonify({"error": "Nama organisasi tidak boleh kosong"}), 400

    org_error = _validate_org_name(name)
    if org_error:
        return jsonify({"error": org_error}), 400

    result = orgs_col.update_one(
        {"_id": ObjectId(org_id)},
        {"$set": {"name": name, "updated_at": datetime.datetime.utcnow()}}
    )
    if result.matched_count == 0:
        return jsonify({"error": "Organization not found"}), 404

    log_event(
        "auth_service",
        f"Organization renamed to {name}",
        user_id=current_user.get('user_id'),
        org_id=org_id,
        action="ORGANIZATION_UPDATE"
    )

    return jsonify({"message": "Organization updated successfully", "org_name": name}), 200


@auth_bp.route('/delegations', methods=['POST'])
@token_required
@role_required('owner')
def create_delegation(current_user):
    """
    Create New Delegation (Owner Only)
    ---
    tags:
      - Enterprise
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
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
    data = request.get_json(force=True, silent=True) or {}
    name = data.get('name', '').strip()
    org_id = current_user.get('org_id')

    if not name:
        return jsonify({"error": "Delegation name is required"}), 400

    delegation = {"name": name, "org_id": org_id, "created_at": datetime.datetime.utcnow()}
    result = delegations_col.insert_one(delegation)
    delegation['_id'] = str(result.inserted_id)
    delegation['created_at'] = delegation['created_at'].isoformat()

    log_event(
        "auth_service",
        f"Membuat divisi baru '{name}'",
        user_id=current_user.get('user_id'),
        org_id=org_id,
        action="DELEGATION_CREATE",
        audience="owner",
        visibility="app",
        severity="info"
    )

    return jsonify(delegation), 201


@auth_bp.route('/delegations', methods=['GET'])
@token_required
def list_delegations(current_user):
    """
    List All Delegations in Organization
    ---
    tags:
      - Enterprise
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
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
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
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
    data = request.get_json(force=True, silent=True) or {}
    target_user_id = data.get('target_user_id')
    new_del_id = data.get('new_delegation_id')

    if not target_user_id:
        return jsonify({"error": "Missing target user ID"}), 400

    try:
        target_user = users_col.find_one({"_id": ObjectId(target_user_id), "org_id": org_id})
    except Exception:
        return jsonify({"error": "Invalid user ID format"}), 400

    if not target_user:
        return jsonify({"error": "Invalid target user"}), 404

    # If moving to general
    if not new_del_id or new_del_id == "general":
        users_col.update_one({"_id": ObjectId(target_user_id)}, {"$set": {"delegation_id": None}})
        docs_col.update_many({"uploaded_by": target_user_id}, {"$set": {"delegation_id": None}})
        docs_col.update_many({"uploaded_by": ObjectId(target_user_id)}, {"$set": {"delegation_id": None}})
        log_event(
            "auth_service",
            f"Memindahkan anggota {target_user['username']} ke Umum (General)",
            user_id=current_user.get('user_id'),
            org_id=org_id,
            action="MEMBER_DELEGATION_CHANGED",
            metadata={
                "target_user_id": target_user_id,
                "target_username": target_user["username"],
                "new_delegation_id": None,
                "new_delegation_name": "General",
            },
            audience="owner",
            visibility="app",
            severity="info",
        )
        return jsonify({"message": f"Anggota {target_user['username']} berhasil dipindahkan ke Umum (General)"}), 200

    try:
        new_delegation = delegations_col.find_one({"_id": ObjectId(new_del_id), "org_id": org_id})
    except Exception:
        return jsonify({"error": "Invalid delegation ID format"}), 400

    if not new_delegation:
        return jsonify({"error": "Invalid delegation"}), 404

    users_col.update_one({"_id": ObjectId(target_user_id)}, {"$set": {"delegation_id": new_del_id}})
    docs_col.update_many({"uploaded_by": target_user_id}, {"$set": {"delegation_id": new_del_id}})
    docs_col.update_many({"uploaded_by": ObjectId(target_user_id)}, {"$set": {"delegation_id": new_del_id}})
    log_event(
        "auth_service",
        f"Memindahkan anggota {target_user['username']} ke divisi {new_delegation['name']}",
        user_id=current_user.get('user_id'),
        org_id=org_id,
        action="MEMBER_DELEGATION_CHANGED",
        metadata={
            "target_user_id": target_user_id,
            "target_username": target_user["username"],
            "new_delegation_id": new_del_id,
            "new_delegation_name": new_delegation["name"],
        },
        audience="owner",
        visibility="app",
        severity="info",
    )

    return jsonify({"message": f"Anggota {target_user['username']} berhasil dipindahkan ke divisi {new_delegation['name']}"}), 200


@auth_bp.route('/assets', methods=['POST'])
@token_required
@role_required('owner')
def upload_asset(current_user):
    """
    Upload Letterhead or Signature (Owner Only)
    ---
    tags:
      - Enterprise
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
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
    data = request.get_json(force=True, silent=True) or {}
    asset_type = data.get('type')
    delegation_id = data.get('delegation_id')
    image_data = data.get('image_data') 
    name = data.get('name', 'Tanpa Nama').strip()
    org_id = current_user.get('org_id')

    normalized_type = "letterhead" if asset_type in ['kop', 'letterhead'] else "signature" if asset_type in ['ttd', 'signature'] else asset_type

    # Normalize delegation_id: if general or empty, set to None
    if not delegation_id or delegation_id == 'general' or delegation_id == '':
        normalized_delegation_id = None
    else:
        normalized_delegation_id = delegation_id

    assets_col.update_one(
        {"type": normalized_type, "org_id": org_id, "name": name},
        {
            "$set": {
                "type": normalized_type,
                "delegation_id": normalized_delegation_id,
                "org_id": org_id,
                "name": name,
                "image_data": image_data,
                "updated_at": datetime.datetime.utcnow()
            },
            "$setOnInsert": {
                "is_active": False
            }
        },
        upsert=True
    )

    asset_type_label = "Kop Surat" if normalized_type == "letterhead" else "Tanda Tangan"
    log_event(
        "auth_service",
        f"Mengunggah aset {asset_type_label} baru '{name}'",
        user_id=current_user.get('user_id'),
        org_id=org_id,
        action="ASSET_UPLOAD",
        audience="owner",
        visibility="app",
        severity="info"
    )

    return jsonify({"message": f"Asset {asset_type} ({name}) uploaded successfully"}), 201


@auth_bp.route('/assets', methods=['GET'])
@token_required
def list_assets(current_user):
    """
    List All Assets (Kop & TTD) in Organization
    """
    org_id = current_user.get('org_id')

    # Prefetch all delegations to avoid N+1 query
    try:
        delegations = list(delegations_col.find({"org_id": org_id}))
        delegation_map = {str(d["_id"]): d.get("name") for d in delegations}
    except Exception:
        delegation_map = {}

    assets = list(assets_col.find({"org_id": org_id}))
    asset_list = []
    for a in assets:
        delegation_name = None
        del_id = a.get('delegation_id')
        if del_id:
            delegation_name = delegation_map.get(str(del_id))
        asset_list.append({
            "id": str(a['_id']),
            "type": "kop" if a.get('type') == "letterhead" else "ttd" if a.get('type') == "signature" else a.get('type'),
            "name": a.get('name', 'Tanpa Nama'),
            "delegation_id": del_id,
            "delegation_name": delegation_name,
            "image_data": a.get('image_data'),
            "is_active": a.get('is_active', False)
        })
    return jsonify(asset_list), 200


@auth_bp.route('/assets/by-delegation/<delegation_id>', methods=['GET'])
@token_required
def get_assets_by_delegation(current_user, delegation_id):
    """
    Get Assets (Kop & TTD) for a Specific Delegation
    """
    org_id = current_user.get('org_id')
    assets = list(assets_col.find({"org_id": org_id, "delegation_id": delegation_id}))
    asset_list = []
    for a in assets:
        asset_list.append({
            "id": str(a['_id']),
            "type": "kop" if a.get('type') == "letterhead" else "ttd" if a.get('type') == "signature" else a.get('type'),
            "name": a.get('name', 'Tanpa Nama'),
            "delegation_id": a.get('delegation_id'),
            "image_data": a.get('image_data'),
            "is_active": a.get('is_active', False)
        })
    return jsonify(asset_list), 200


@auth_bp.route('/assets/<asset_id>', methods=['DELETE'])
@token_required
@role_required('owner')
def delete_asset(current_user, asset_id):
    """
    Delete an Asset (Owner Only)
    ---
    tags:
      - Enterprise
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
      - name: asset_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Asset deleted
      404:
        description: Asset not found
    """
    org_id = current_user.get('org_id')
    try:
        # Fetch target asset details first for logging
        target_asset = assets_col.find_one({"_id": ObjectId(asset_id), "org_id": org_id})
        asset_name = target_asset.get('name', 'Tanpa Nama') if target_asset else 'Tanpa Nama'
        asset_type_label = "Kop Surat" if target_asset and target_asset.get('type') == 'letterhead' else "Tanda Tangan" if target_asset and target_asset.get('type') == 'signature' else "Aset"

        result = assets_col.delete_one({"_id": ObjectId(asset_id), "org_id": org_id})
        if result.deleted_count == 0:
            return jsonify({"error": "Asset not found"}), 404

        log_event(
            "auth_service",
            f"Menghapus aset {asset_type_label} '{asset_name}'",
            user_id=current_user.get('user_id'),
            org_id=org_id,
            action="ASSET_DELETE",
            audience="owner",
            visibility="app",
            severity="info"
        )
        return jsonify({"message": "Asset deleted successfully"}), 200
    except Exception as e:
        log_event("auth_service", f"Invalid asset ID for deletion: {str(e)}", org_id=org_id, severity="error")
        return jsonify({"error": "Invalid asset ID"}), 400


@auth_bp.route('/assets/<asset_id>', methods=['PUT'])
@token_required
@role_required('owner')
def update_asset(current_user, asset_id):
    """
    Update an Asset Name or Image (Owner Only)
    ---
    tags:
      - Enterprise
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
      - name: asset_id
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            image_data:
              type: string
              description: Base64 image string (optional, only if replacing image)
    responses:
      200:
        description: Asset updated
      404:
        description: Asset not found
    """
    org_id = current_user.get('org_id')
    data = request.get_json(force=True, silent=True) or {}

    update_fields = {"updated_at": datetime.datetime.utcnow()}
    if 'name' in data and data['name'].strip():
        update_fields['name'] = data['name'].strip()
    if 'image_data' in data and data['image_data']:
        update_fields['image_data'] = data['image_data']
    if 'is_active' in data:
        update_fields['is_active'] = bool(data['is_active'])

    if len(update_fields) <= 1:
        return jsonify({"error": "No fields to update"}), 400

    try:
        target_asset = assets_col.find_one({"_id": ObjectId(asset_id), "org_id": org_id})
        if not target_asset:
            return jsonify({"error": "Asset not found"}), 404

        # Exclusive activation: if activating this asset, deactivate all other assets
        # of the same type and delegation in this org
        if update_fields.get('is_active') == True:
            try:
                same_type = target_asset.get('type')
                same_delegation = target_asset.get('delegation_id')
                
                # Normalize delegation query to cover None, "general", ""
                if not same_delegation or same_delegation == 'general' or same_delegation == '':
                    delegation_query = {"$in": [None, "general", ""]}
                else:
                    delegation_query = same_delegation

                # Deactivate all other assets with same type + delegation in this org
                assets_col.update_many(
                    {
                        "_id": {"$ne": ObjectId(asset_id)},
                        "type": same_type,
                        "delegation_id": delegation_query,
                        "org_id": org_id
                    },
                    {"$set": {"is_active": False}}
                )
            except Exception as ex:
                print(f"Exclusive activation error: {ex}")

        result = assets_col.update_one(
            {"_id": ObjectId(asset_id), "org_id": org_id},
            {"$set": update_fields}
        )
        if result.matched_count == 0:
            return jsonify({"error": "Asset not found"}), 404

        # Determine the log message based on what fields were updated
        asset_type_label = "Kop Surat" if target_asset.get('type') == "letterhead" else "Tanda Tangan"
        old_name = target_asset.get('name', 'Tanpa Nama')
        
        log_msgs = []
        if 'name' in update_fields:
            log_msgs.append(f"mengubah nama aset {asset_type_label} dari '{old_name}' menjadi '{update_fields['name']}'")
        if 'image_data' in update_fields:
            log_msgs.append(f"memperbarui berkas gambar aset {asset_type_label} '{update_fields.get('name', old_name)}'")
        if 'is_active' in update_fields:
            status_str = "mengaktifkan" if update_fields['is_active'] else "menonaktifkan"
            log_msgs.append(f"{status_str} aset {asset_type_label} '{update_fields.get('name', old_name)}'")
            
        log_message = ", ".join(log_msgs)
        if log_message:
            log_message = log_message[0].upper() + log_message[1:]
        else:
            log_message = f"Memperbarui aset {asset_type_label} '{old_name}'"

        log_event(
            "auth_service",
            log_message,
            user_id=current_user.get('user_id'),
            org_id=org_id,
            action="ASSET_UPDATE",
            audience="owner",
            visibility="app",
            severity="info"
        )
        return jsonify({"message": "Asset updated successfully"}), 200
    except Exception as e:
        log_event("auth_service", f"Invalid asset ID for update: {str(e)}", org_id=org_id, severity="error")
        return jsonify({"error": "Invalid asset ID"}), 400


@auth_bp.route('/delegations/<delegation_id>', methods=['PUT'])
@token_required
@role_required('owner')
def update_delegation(current_user, delegation_id):
    """
    Update Delegation/Division Name (Owner Only)
    """
    data = request.get_json(force=True, silent=True) or {}
    name = data.get('name', '').strip()
    org_id = current_user.get('org_id')

    if not name:
        return jsonify({"error": "Delegation name is required"}), 400

    try:
        # Get old name first for logging
        delegation = delegations_col.find_one({"_id": ObjectId(delegation_id), "org_id": org_id})
        old_name = delegation.get('name') if delegation else 'Divisi'

        result = delegations_col.update_one(
            {"_id": ObjectId(delegation_id), "org_id": org_id},
            {"$set": {"name": name}}
        )
        if result.matched_count == 0:
            return jsonify({"error": "Delegation not found"}), 404

        log_event(
            "auth_service",
            f"Mengubah nama divisi '{old_name}' menjadi '{name}'", 
            user_id=current_user.get('user_id'),
            org_id=org_id,
            action="DELEGATION_RENAME",
            audience="owner",
            visibility="app",
            severity="info"
        )
        return jsonify({"message": "Delegation name updated successfully"}), 200
    except Exception as e:
        log_event("auth_service", f"Invalid delegation ID for update: {str(e)}", org_id=org_id, severity="error")
        return jsonify({"error": "Invalid delegation ID format"}), 400


@auth_bp.route('/delegations/<delegation_id>', methods=['DELETE'])
@token_required
@role_required('owner')
def delete_delegation(current_user, delegation_id):
    """
    Delete Delegation/Division (Owner Only)
    """
    org_id = current_user.get('org_id')
    try:
        delegation = delegations_col.find_one({"_id": ObjectId(delegation_id), "org_id": org_id})
        if not delegation:
            return jsonify({"error": "Delegation not found"}), 404
            
        # Update all users under this division to None
        users_col.update_many({"delegation_id": delegation_id, "org_id": org_id}, {"$set": {"delegation_id": None}})
        
        # Update all documents under this division to None
        docs_col.update_many({"delegation_id": delegation_id}, {"$set": {"delegation_id": None}})
        docs_col.update_many({"delegation_id": ObjectId(delegation_id)}, {"$set": {"delegation_id": None}})
        
        # Finally delete the delegation itself
        delegations_col.delete_one({"_id": ObjectId(delegation_id)})
        
        log_event(
            "auth_service",
            f"Menghapus divisi '{delegation.get('name')}'", 
            user_id=current_user.get('user_id'),
            org_id=org_id,
            action="DELEGATION_DELETE",
            audience="owner",
            visibility="app",
            severity="info"
        )
        return jsonify({"message": "Delegation deleted successfully and members migrated to general"}), 200
    except Exception as e:
        log_event("auth_service", f"Invalid delegation ID for deletion: {str(e)}", org_id=org_id, severity="error")
        return jsonify({"error": "Invalid delegation ID format"}), 400


@auth_bp.route('/members', methods=['GET'])
@token_required
def list_members(current_user):
    """
    List All Members in Organization
    ---
    tags:
      - Enterprise
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
    responses:
      200:
        description: List of organization members
      401:
        description: Unauthorized
    """
    org_id = current_user.get('org_id')
    if not org_id:
        return jsonify([]), 200

    try:
        # Prefetch all delegations to avoid N+1 queries
        try:
            delegations = list(delegations_col.find({"org_id": org_id}))
            delegation_map = {str(d["_id"]): d.get("name") for d in delegations}
        except Exception:
            delegation_map = {}

        users = list(users_col.find({"org_id": org_id}))
        member_list = []
        for u in users:
            # Look up delegation name if delegation_id exists from pre-fetched map
            delegation_name = None
            del_id = u.get('delegation_id')
            if del_id:
                delegation_name = delegation_map.get(str(del_id))

            member_list.append({
                "id": str(u['_id']),
                "username": u['username'],
                "email": u['email'],
                "role": u.get('role', 'member'),
                "delegation_id": del_id,
                "delegation_name": delegation_name
            })
        return jsonify(member_list), 200
    except Exception as e:
        log_event("auth_service", f"Failed to retrieve members: {str(e)}", org_id=org_id, severity="error")
        return jsonify({"error": "Failed to retrieve members"}), 500


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
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
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
    data = request.get_json(force=True, silent=True) or {}
    email = data.get('email', '').strip().lower()
    role = data.get('role', 'member')
    org_id = current_user.get('org_id')

    if not email:
        return jsonify({"error": "Email is required"}), 400

    # Retrieve organization name
    org = None
    if org_id:
        try:
            org = orgs_col.find_one({"_id": ObjectId(org_id) if isinstance(org_id, str) else org_id})
        except Exception:
            org = orgs_col.find_one({"_id": org_id})
    org_name = org.get('name') if org else "Personal Workspace"
    inviter_name = current_user.get('username') or current_user.get('email') or "Admin"

    # Send beautiful HTML invitation email first
    mail_success, mail_msg = send_invitation_email(email, org_name, inviter_name)
    
    if not mail_success:
        log_event("auth_service", f"Failed to send email to {email}: {mail_msg}", action="INVITE_EMAIL_FAILED")
        return jsonify({
            "error": f"Gagal mengirim email undangan: {mail_msg}. Pastikan konfigurasi SMTP di file .env sudah benar."
        }), 400

    # Store invitation state in MongoDB ONLY if email was successfully sent
    invitations_col.insert_one({
        "email": email, 
        "org_id": org_id, 
        "role": role, 
        "status": "pending", 
        "created_at": datetime.datetime.utcnow()
    })
    log_event(
        "auth_service",
        f"Mengirim undangan bergabung ke {email}",
        user_id=current_user.get("user_id"),
        org_id=org_id,
        action="INVITE_MEMBER_SUCCESS",
        metadata={"email": email, "role": role},
        audience="owner",
        visibility="app",
        severity="info",
    )

    return jsonify({"message": "Invitation sent successfully to email"}), 201


@auth_bp.route('/change-password', methods=['POST'])
@token_required
def change_password(current_user):
    """
    Change Password (Authenticated)
    ---
    tags:
      - Auth
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - old_password
            - new_password
          properties:
            old_password:
              type: string
            new_password:
              type: string
    responses:
      200:
        description: Password updated successfully
      401:
        description: Invalid old password
    """
    data = request.get_json(force=True, silent=True) or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return jsonify({"error": "Missing old or new password"}), 400

    user_id = current_user.get('user_id')
    user = users_col.find_one({"_id": ObjectId(user_id)})

    if not user or not check_password_hash(user['password'], old_password):
        return jsonify({"error": "Invalid old password"}), 401

    p_error = _validate_password(new_password)
    if p_error:
        return jsonify({"error": p_error}), 400

    hashed_password = generate_password_hash(new_password)
    users_col.update_one({"_id": ObjectId(user_id)}, {"$set": {"password": hashed_password}})

    log_event("auth_service", f"Password changed for user: {user['username']}", user_id=user_id)

    return jsonify({"message": "Password updated successfully"}), 200


@auth_bp.route('/delete-account', methods=['DELETE'])
@token_required
def delete_account(current_user):
    """
    Delete User Account (Authenticated)
    ---
    tags:
      - Auth
    security:
      - BearerAuth: []
    responses:
      200:
        description: Account deleted successfully
      404:
        description: User not found
    """
    user_id = current_user.get('user_id')
    user = users_col.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Delete the user from users collection
    users_col.delete_one({"_id": ObjectId(user_id)})

    log_event("auth_service", f"User account deleted for user: {user.get('username') or user.get('email')}", user_id=user_id, action="ACCOUNT_DELETED")

    return jsonify({"message": "Akun Anda telah berhasil dihapus selamanya."}), 200


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """
    Request Password Reset OTP
    ---
    tags:
      - Auth
    consumes:
      - application/json
    produces:
      - application/json
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
              example: "user@example.com"
    responses:
      200:
        description: OTP sent to email
      404:
        description: User not found
    """
    data = request.get_json(force=True, silent=True) or {}
    email = data.get('email', '').strip().lower()

    if not email:
        return jsonify({"error": "Email is required"}), 400

    user = users_col.find_one({"email": email})
    if not user:
        return jsonify({"error": "User with this email does not exist"}), 404

    # Generate 6-digit OTP
    otp_code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)

    # Store/Update OTP in database
    otps_col.update_one(
        {"email": email},
        {"$set": {"otp": otp_code, "expiry": expiry, "created_at": datetime.datetime.utcnow()}},
        upsert=True
    )

    # Send email
    success, message = send_otp_email(email, otp_code)
    
    if not success:
        return jsonify({"error": f"Failed to send email: {message}"}), 500

    log_event("auth_service", f"OTP sent to {email}", user_id=str(user['_id']))

    return jsonify({"message": "OTP has been sent to your email"}), 200


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """
    Reset Password using OTP
    ---
    tags:
      - Auth
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - email
            - otp
            - new_password
          properties:
            email:
              type: string
            otp:
              type: string
            new_password:
              type: string
    responses:
      200:
        description: Password reset successful
      400:
        description: Invalid OTP or expired
    """
    data = request.get_json(force=True, silent=True) or {}
    email = data.get('email', '').strip().lower()
    otp_input = data.get('otp', '').strip()
    new_password = data.get('new_password', '')

    if not email or not otp_input or not new_password:
        return jsonify({"error": "Missing required fields"}), 400

    # Validate new password
    p_error = _validate_password(new_password)
    if p_error:
        return jsonify({"error": p_error}), 400

    # Check OTP
    otp_record = otps_col.find_one({"email": email})
    
    if not otp_record:
        return jsonify({"error": "No OTP found for this email"}), 400
    
    if otp_record['otp'] != otp_input:
        return jsonify({"error": "Invalid OTP code"}), 400
    
    if datetime.datetime.utcnow() > otp_record['expiry']:
        return jsonify({"error": "OTP has expired"}), 400

    # Update Password
    hashed_password = generate_password_hash(new_password)
    users_col.update_one({"email": email}, {"$set": {"password": hashed_password}})

    # Delete used OTP
    otps_col.delete_one({"email": email})

    log_event("auth_service", f"Password reset successful for {email}")

    return jsonify({"message": "Password has been reset successfully"}), 200


@auth_bp.route('/google/disconnect', methods=['POST'])
@token_required
@role_required('owner')
def google_disconnect(current_user):
    """
    Disconnect Google Drive Account
    ---
    tags:
      - Integration
    security:
      - BearerAuth: []
    responses:
      200:
        description: Google Drive successfully disconnected
      500:
        description: Failed to disconnect
    """
    user_id = current_user.get("user_id")
    try:
        users_col.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "google_drive_connected": False,
                    "google_oauth": {}
                }
            }
        )
        log_event(
            "auth_service",
            f"User {user_id} disconnected Google Drive",
            user_id=user_id,
            action="GOOGLE_DRIVE_DISCONNECTED",
            audience="owner",
            visibility="app",
            severity="info",
        )
        return jsonify({"message": "Google Drive berhasil diputuskan."}), 200
    except Exception as e:
        log_event("auth_service", f"Gagal memutuskan Google Drive: {str(e)}", user_id=user_id, action="GOOGLE_DRIVE_DISCONNECT_FAILED", severity="error")
        return jsonify({"error": "Gagal memutuskan koneksi Google Drive"}), 500


@auth_bp.route('/google/connect', methods=['GET'])
@token_required
def google_connect(current_user):
    """
    Get Google OAuth 2.0 Consent Screen URL
    ---
    tags:
      - Integration
    security:
      - BearerAuth: []
    responses:
      200:
        description: Returns the URL to redirect the user to Google Login
    """
    import urllib.parse
    
    user_id = current_user.get("user_id")
    client_id = Config.GOOGLE_CLIENT_ID
    redirect_uri = urllib.parse.quote(Config.GOOGLE_REDIRECT_URI)
    scope = urllib.parse.quote("https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/calendar")
    
    # State berisi user_id agar saat callback kita tahu siapa yang melakukan otorisasi
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        "response_type=code&"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"scope={scope}&"
        "access_type=offline&"
        "prompt=consent&"
        f"state={user_id}"
    )
    
    return jsonify({"auth_url": auth_url}), 200


@auth_bp.route('/google/callback', methods=['GET'])
def google_callback():
    """
    Callback Google OAuth 2.0 untuk menerima authorization code
    """
    code = request.args.get("code")
    user_id = request.args.get("state")
    
    if not code or not user_id:
        return "<h3>Error: Otorisasi Google Drive tidak valid (Missing code or state)</h3>", 400
        
    # Tukar authorization code dengan tokens
    payload = {
        "client_id": Config.GOOGLE_CLIENT_ID,
        "client_secret": Config.GOOGLE_CLIENT_SECRET,
        "code": code,
        "redirect_uri": Config.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    
    try:
        res = requests.post("https://oauth2.googleapis.com/token", data=payload, timeout=10)
        if res.status_code != 200:
            log_event("auth_service", f"Gagal menukar token Google: {res.text}", user_id=user_id, action="GOOGLE_TOKEN_EXCHANGE_FAILED", metadata={"response": res.text, "status_code": res.status_code})
            return f"<h3>Gagal menukar token Google: {res.text}</h3>", 400
            
        token_data = res.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        expiry_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)
        
        # Simpan tokens di database MongoDB koleksi users_col menggunakan dot-notation
        update_data = {
            "google_drive_connected": True,
            "google_oauth.access_token": access_token,
            "google_oauth.token_expiry": expiry_time
        }
        
        if refresh_token:
            update_data["google_oauth.refresh_token"] = refresh_token
            
        result = users_col.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            return "<h3>Error: Pengguna tidak ditemukan di sistem.</h3>", 404
            
        log_event(
            "auth_service",
            f"Google Drive successfully connected for user: {user_id}",
            user_id=user_id,
            action="GOOGLE_DRIVE_CONNECTED",
            audience="owner",
            visibility="app",
            severity="info",
        )
        
        # Memicu migrasi dokumen lama dari MongoDB ke Google Drive
        try:
            requests.post(
                f"{Config.GATEWAY_URL}/document/migrate-to-drive", 
                json={"user_id": user_id}, 
                headers={"Authorization": request.headers.get("Authorization", "")}, 
                timeout=1
            )
        except Exception:
            # Abaikan timeout karena pemanggilan async/background
            pass
            
        return """
        <html>
            <head>
                <title>Koneksi Sukses</title>
                <style>
                    body { font-family: sans-serif; text-align: center; padding-top: 50px; background-color: #f7f9fa; }
                    .container { max-width: 500px; margin: 0 auto; padding: 30px; background: white; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
                    h2 { color: #2e7d32; }
                    p { color: #555; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>Koneksi Google Drive Berhasil!</h2>
                    <p>Akun Google Drive Anda telah sukses terhubung ke AmbaNotes.</p>
                    <p>Semua dokumen fisik Anda sedang dipindahkan ke Drive pribadi Anda secara aman.</p>
                    <p>Anda dapat menutup halaman ini sekarang dan kembali ke aplikasi.</p>
                </div>
            </body>
        </html>
        """, 200
        
    except Exception as e:
        log_event("auth_service", f"Error sewaktu Google Callback: {str(e)}", user_id=user_id, action="GOOGLE_CALLBACK_ERROR", severity="error")
        return "<h3>Terjadi kesalahan sistem sewaktu Google Drive callback</h3>", 500


# ─── Admin / Developers Endpoints ───────────────────────────────

@auth_bp.route('/developers/login', methods=['POST'])
def developers_login():
    data = request.get_json(force=True, silent=True) or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    user = users_col.find_one({"email": email, "role": "admin"})
    if not user or not check_password_hash(user['password'], password):
        return jsonify({"error": "Invalid admin credentials"}), 401
    token = generate_token(user)
    response = jsonify({"token": token, "redirect": "/developers", "user": {"id": str(user['_id']), "username": user['username'], "email": user['email'], "role": "admin"}})
    response.set_cookie("token", token, httponly=True, samesite="Lax", max_age=Config.JWT_EXP_HOURS * 3600, path="/")
    return response, 200

@auth_bp.route('/developers/stats', methods=['GET'])
@token_required
@role_required('admin')
def developers_stats(current_user):
    total_docs = docs_col.count_documents({})
    total_chats = chats_col.count_documents({})
    return jsonify({
        "total_organizations": orgs_col.count_documents({}),
        "total_users": users_col.count_documents({}),
        "total_documents": total_docs,
        "total_chat_sessions": total_chats,
    }), 200

@auth_bp.route('/developers/organizations', methods=['GET'])
@token_required
@role_required('admin')
def developers_organizations(current_user):
    orgs = list(orgs_col.find())
    result = []
    for org in orgs:
        oid = str(org['_id'])
        members = users_col.count_documents({"org_id": oid})
        docs_c = docs_col.count_documents({"org_id": oid})
        created = org.get("created_at")
        if created:
            created_str = created.isoformat() if hasattr(created, 'isoformat') else str(created)
        else:
            created_str = None
        result.append({
            "id": oid,
            "name": org.get("name"),
            "invite_code": org.get("invite_code"),
            "created_at": created_str,
            "members": members,
            "documents": docs_c,
        })
    return jsonify(result), 200

@auth_bp.route('/developers/organization/<org_id>', methods=['DELETE'])
@token_required
@role_required('admin')
def developers_delete_org(current_user, org_id):
    try:
        org = orgs_col.find_one({"_id": ObjectId(org_id)})
    except Exception:
        return jsonify({"error": "Invalid org ID"}), 400
    if not org:
        return jsonify({"error": "Organization not found"}), 404
    org_name = org.get("name", "Unknown")
    users_col.delete_many({"org_id": org_id})
    docs_col.delete_many({"org_id": org_id})
    reminders_col.delete_many({"org_id": org_id})
    invitations_col.delete_many({"org_id": org_id})
    delegations_col.delete_many({"org_id": org_id})
    assets_col.delete_many({"org_id": org_id})
    logs_col.delete_many({"org_id": org_id})
    orgs_col.delete_one({"_id": ObjectId(org_id)})
    log_event("auth_service", f"Admin deleted organization '{org_name}' ({org_id})", action="ADMIN_DELETE_ORG")
    return jsonify({"message": f"Organization '{org_name}' and all associated data deleted"}), 200

@auth_bp.route('/developers/users', methods=['GET'])
@token_required
@role_required('admin')
def developers_users(current_user):
    users_list = list(users_col.find())
    result = []
    for u in users_list:
        org_name = None
        if u.get("org_id"):
            org = orgs_col.find_one({"_id": ObjectId(u['org_id']) if isinstance(u['org_id'], str) else u['org_id']})
            if org:
                org_name = org.get("name")
        delegation_name = None
        if u.get("delegation_id"):
            try:
                del_obj = delegations_col.find_one({"_id": ObjectId(u["delegation_id"])})
                delegation_name = del_obj.get("name") if del_obj else None
            except Exception:
                pass
        created = u.get("created_at")
        if created:
            created_str = created.isoformat() if hasattr(created, 'isoformat') else str(created)
        else:
            created_str = None
        result.append({
            "id": str(u['_id']),
            "username": u.get("username"),
            "email": u.get("email"),
            "role": u.get("role"),
            "org_id": u.get("org_id"),
            "org_name": org_name,
            "delegation_id": u.get("delegation_id"),
            "delegation_name": delegation_name,
            "created_at": created_str,
        })
    return jsonify(result), 200

@auth_bp.route('/developers/user/<user_id>', methods=['DELETE'])
@token_required
@role_required('admin')
def developers_delete_user(current_user, user_id):
    try:
        user = users_col.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return jsonify({"error": "Invalid user ID"}), 400
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.get("role") in ("admin", "owner"):
        return jsonify({"error": "Cannot delete admin or owner user. Delete the organization instead."}), 403
    username = user.get("username", "Unknown")
    org_id = user.get("org_id")
    if org_id:
        owner = users_col.find_one({"org_id": org_id, "role": "owner"})
        if owner:
            owner_id = str(owner["_id"])
            docs_col.update_many({"uploaded_by": user_id}, {"$set": {"uploaded_by": owner_id}})
            docs_col.update_many({"uploaded_by": ObjectId(user_id)}, {"$set": {"uploaded_by": owner_id}})
        reminders_col.delete_many({"created_by": user_id})
        reminders_col.delete_many({"created_by": ObjectId(user_id)})
    users_col.delete_one({"_id": ObjectId(user_id)})
    log_event("auth_service", f"Admin deleted user '{username}' ({user_id})", action="ADMIN_DELETE_USER")
    return jsonify({"message": f"User '{username}' deleted"}), 200

@auth_bp.route('/developers/activity-logs', methods=['GET'])
@token_required
@role_required('admin')
def developers_activity_logs(current_user):
    limit = request.args.get('limit', default=100, type=int)
    limit = max(1, min(limit, 500))
    logs = list(logs_col.find().sort("timestamp", -1).limit(limit))
    result = []
    for item in logs:
        ts = item.get("timestamp")
        result.append({
            "id": str(item.get("_id")),
            "service": item.get("service"),
            "message": item.get("message"),
            "action": item.get("action"),
            "severity": item.get("severity", "info"),
            "user_id": item.get("user_id"),
            "org_id": item.get("org_id"),
            "metadata": item.get("metadata", {}),
            "timestamp": ts.isoformat() if ts else None,
        })
    return jsonify(result), 200

@auth_bp.route('/developers/health', methods=['GET'])
@token_required
@role_required('admin')
def developers_health(current_user):
    services = {
        "api-gateway": "http://api-gateway:5009",
        "document-pipeline": "http://document-pipeline:5001",
        "ai-service": "http://ai-service:5002",
        "support-services": "http://support-services:5003",
        "graphql-service": "http://graphql-service:5004",
    }
    result = {}
    for name, url in services.items():
        try:
            r = requests.get(f"{url}/health", timeout=3)
            result[name] = {"status": "healthy" if r.status_code == 200 else "degraded", "code": r.status_code}
        except requests.RequestException:
            result[name] = {"status": "unreachable", "code": None}
    return jsonify(result), 200


@auth_bp.route('/developers/document-trends', methods=['GET'])
@token_required
@role_required('admin')
def developers_trends(current_user):
    now = datetime.datetime.utcnow()
    weeks = []
    for i in range(7, -1, -1):
        start = now - datetime.timedelta(days=i * 7 + 7)
        end = now - datetime.timedelta(days=i * 7)
        count = docs_col.count_documents({"uploaded_at": {"$gte": start, "$lt": end}})
        label = start.strftime("%d %b")
        weeks.append({"label": label, "count": count})
    return jsonify(weeks), 200


@auth_bp.route('/developers/instagram-insights', methods=['GET'])
@token_required
@role_required('admin')
def developers_instagram(current_user):
    try:
        auth = request.headers.get("Authorization", "")
        cookie_token = request.cookies.get("token", "")
        headers = {}
        if auth:
            headers["Authorization"] = auth
        elif cookie_token:
            headers["Authorization"] = f"Bearer {cookie_token}"
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        target = "http://support-services:5003/insight/api/insights"
        params = {}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        resp = requests.get(target, headers=headers, params=params, timeout=30)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        log_event("auth_service", f"Instagram insights error: {str(e)}", action="ADMIN_INSTAGRAM_ERROR", severity="error")
        return jsonify({"error": str(e)}), 500


@auth_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "auth_service"}), 200


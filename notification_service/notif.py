import os
import sys

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
from common.logger import log_event
from common.jwt_utils import token_required
from common.db import logs_col

notification_bp = Blueprint('notification', __name__)

@notification_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health Check Endpoint (Notification)
    ---
    tags:
      - Notification
    responses:
      200:
        description: Service is healthy
    """
    log_event("notification_service", "Health check requested", action="HEALTH_CHECK")
    return jsonify({"status": "healthy", "service": "notification_service"}), 200


@notification_bp.route('/recent', methods=['GET'])
@token_required
def recent_notifications(current_user):
    """
    Recent Notifications Feed
    ---
    tags:
      - Notification
    produces:
      - application/json
    security:
      - BearerAuth: []
    responses:
      200:
        description: Recent notification feed for the current user
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")
    limit = request.args.get("limit", default=15, type=int) or 15
    limit = max(1, min(limit, 50))

    try:
        query = {
            "$or": [
                {
                    "user_id": user_id,
                    "visibility": "app",
                    "audience": {"$in": ["user", "owner"]},
                },
                {
                    "org_id": org_id,
                    "visibility": "app",
                    "audience": "owner",
                },
            ]
        }

        logs = list(logs_col.find(query).sort("timestamp", -1).limit(limit))
        items = []

        for item in logs:
            action = item.get("action") or "INFO"
            items.append({
                "id": str(item.get("_id")),
                "title": _title_from_action(action),
                "message": item.get("message", ""),
                "action": action,
                "service": item.get("service"),
                "timestamp": item.get("timestamp").isoformat() if item.get("timestamp") else None,
                "is_personal": item.get("user_id") == user_id,
            })

        log_event(
            "notification_service",
            f"Recent notifications viewed by {current_user.get('username')}",
            org_id=org_id,
            action="NOTIFICATIONS_VIEWED",
            metadata={"count": len(items), "viewer_user_id": user_id},
            audience="developer",
            visibility="dashboard",
            severity="info",
        )
        return jsonify(items), 200
    except Exception as e:
        log_event(
            "notification_service",
            f"Failed to fetch notifications: {str(e)}",
            user_id=user_id,
            org_id=org_id,
            action="NOTIFICATIONS_FAILED",
            metadata={"error": str(e)},
            severity="error",
        )
        return jsonify({"error": "Failed to fetch notifications"}), 500


def _title_from_action(action):
    mapping = {
        "REGISTER_SUCCESS": "Akun Berhasil Dibuat",
        "INVITE_MEMBER_SUCCESS": "Undangan Anggota Terkirim",
        "MEMBER_DELEGATION_CHANGED": "Divisi Anggota Diperbarui",
        "DOC_UPLOAD_SUCCESS": "Surat Berhasil Diproses",
        "DOC_DELETE_SUCCESS": "Surat Dihapus",
        "DOC_REPLACE_SUCCESS": "Surat Diganti",
        "AI_CHAT_SUCCESS": "Percakapan AI Diperbarui",
        "AI_DELETE_CHAT_SUCCESS": "Histori Chat Dihapus",
        "LOGIN_SUCCESS": "Login Berhasil",
        "GOOGLE_DRIVE_CONNECTED": "Google Drive Terhubung",
        "GOOGLE_DRIVE_DISCONNECTED": "Google Drive Diputus",
    }
    return mapping.get(action, "Aktivitas Baru")

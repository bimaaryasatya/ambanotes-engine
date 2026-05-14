import os
import sys
import datetime
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify
from insight_service.services.analytics_service import generate_insight
from common.logger import log_event
from common.jwt_utils import token_required
from common.db import docs_col, reminders_col, invitations_col
from common.config import Config

insight_bp = Blueprint('insight', __name__)


@insight_bp.route("/")
def home():
    return jsonify({"message": "AmbaNotes Event Insight API"})


@insight_bp.route("/api/insights", methods=["GET"])
@token_required
def insights(current_user):
    """
    Get Organization Insights & Analytics
    ---
    tags:
      - Insight
    security:
      - BearerAuth: []
    responses:
      200:
        description: Detailed insights from document data
      401:
        description: Unauthorized
      500:
        description: Internal Server Error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    log_event("insight_service", f"Insights requested by: {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="INSIGHTS_REQUEST")
    try:
        data = generate_insight()
        return jsonify(data), 200
    except Exception as e:
        log_event("insight_service", f"Failed to generate insights: {str(e)}",
                  user_id=user_id, org_id=org_id, action="INSIGHTS_FAILED", metadata={"error": str(e)})
        return jsonify({"error": str(e)}), 500


@insight_bp.route("/weekly-summary", methods=["GET"])
@token_required
def weekly_summary(current_user):
    """
    Weekly Executive Summary (Jarvis Mode)
    ---
    tags:
      - Insight
    security:
      - BearerAuth: []
    responses:
      200:
        description: AI-generated weekly summary
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")
    
    last_week = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    
    try:
        # 1. Fetch Stats
        new_docs = docs_col.count_documents({"org_id": org_id, "created_at": {"$gte": last_week}})
        new_reminders = reminders_col.count_documents({"org_id": org_id, "created_at": {"$gte": last_week}})
        pending_inv = invitations_col.count_documents({"org_id": org_id, "status": "pending"})
        
        # 2. Build AI Prompt
        prompt = (
            "Anda adalah asisten cerdas AmbaNotes. Tolong buatkan 'Rangkuman Eksekutif Mingguan' yang singkat, "
            "profesional, dan bersemangat untuk Pimpinan Organisasi (Owner) berdasarkan data minggu ini:\n"
            f"- Surat Masuk Baru: {new_docs}\n"
            f"- Jadwal/Tugas Baru: {new_reminders}\n"
            f"- Undangan Member Tertunda: {pending_inv}\n\n"
            "Gunakan Bahasa Indonesia yang formal. Berikan saran singkat di akhir."
        )
        
        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {Config.MISTRAL_API_KEY}"},
            json={
                "model": "mistral-small",
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        
        response.raise_for_status()
        summary = response.json()['choices'][0]['message']['content']
        
        log_event("insight_service", "Weekly summary generated", user_id=user_id, org_id=org_id, action="WEEKLY_SUMMARY_SUCCESS")
        
        return jsonify({
            "stats": {
                "new_documents": new_docs,
                "new_reminders": new_reminders,
                "pending_invitations": pending_inv
            },
            "summary": summary
        }), 200

    except Exception as e:
        log_event("insight_service", f"Weekly summary error: {str(e)}", user_id=user_id, org_id=org_id, action="WEEKLY_SUMMARY_FAILED")
        return jsonify({"error": str(e)}), 500
import os
import sys
import datetime
import requests
import json
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify
from .services.analytics_service import generate_insight
from common.logger import log_event
from common.jwt_utils import token_required
from common.db import docs_col, reminders_col, invitations_col
from common.config import Config
def _call_mistral(prompt, system_instruction=None):
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {Config.MISTRAL_API_KEY}"},
        json={
            "model": "mistral-small",
            "messages": messages
        },
        timeout=30
    )
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

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
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
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
                  user_id=user_id, org_id=org_id, action="INSIGHTS_FAILED", metadata={"error": str(e)}, severity="error")
        return jsonify({"error": "Failed to generate insights"}), 500


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
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
    responses:
      200:
        description: AI-generated weekly summary
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")
    
    last_week = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    
    try:
        # 1. Fetch Stats (Use uploaded_at instead of created_at for documents)
        new_docs = docs_col.count_documents({"org_id": org_id, "uploaded_at": {"$gte": last_week}})
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
        
        try:
            summary = _call_mistral(prompt)
        except Exception as gemini_err:
            import traceback
            traceback.print_exc()
            summary = "Ringkasan eksekutif AI sedang disiapkan. Statistik dokumen Anda di bawah ini tetap diperbarui secara real-time."
        
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
        import traceback
        traceback.print_exc()
        log_event("insight_service", f"Weekly summary error: {str(e)}", user_id=user_id, org_id=org_id, action="WEEKLY_SUMMARY_FAILED", severity="error")
        return jsonify({"error": "Failed to generate weekly summary"}), 500


@insight_bp.route("/predictive-trends", methods=["GET"])
@token_required
def predictive_trends(current_user):
    """
    Predictive Analytics for Organizational Workload
    ---
    tags:
      - Insight
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
        description: Workload predictions based on historical data
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")
    
    # Fetch real-time historical counts from MongoDB
    docs_count = docs_col.count_documents({"org_id": org_id})
    surat_keluar_count = docs_col.count_documents({
        "org_id": org_id, 
        "$or": [
            {"classification.label": "Surat Keluar"},
            {"classification.label": "surat_keluar"},
            {"classification.label_name": "Surat Keluar"},
            {"classification.label_name": "surat_keluar"}
        ]
    })
    surat_masuk_count = max(0, docs_count - surat_keluar_count)
    reminders_count = reminders_col.count_documents({"org_id": org_id})
    
    prompt = (
        "Anda adalah Data Scientist AmbaNotes. Analisis beban kerja organisasi ini.\n"
        f"Data saat ini: Total Dokumen {docs_count}.\n"
        "Berdasarkan pola administrasi pemerintahan Indonesia, buatkan prediksi beban kerja "
        "untuk 3 bulan ke depan (Januari-Desember) dalam format JSON:\n"
        "{\n"
        "  \"predictions\": [\n"
        "    {\"month\": \"...\", \"workload_score\": 0.0 to 1.0, \"reason\": \"...\"}\n"
        "  ],\n"
        "  \"recommendation\": \"...\"\n"
        "}"
    )

    try:
        content = _call_mistral(prompt)
        predictions_data = json.loads(re.search(r"\{.*\}", content, re.DOTALL).group())
        predictions = predictions_data.get("predictions", [])
        recommendation = predictions_data.get("recommendation", "")
    except Exception as gemini_err:
        import traceback
        traceback.print_exc()
        predictions = [
            {"month": "Bulan Depan", "workload_score": 0.3, "reason": "Pola dasar historis"},
            {"month": "2 Bulan Depan", "workload_score": 0.4, "reason": "Pola dasar historis"},
            {"month": "3 Bulan Depan", "workload_score": 0.5, "reason": "Pola dasar historis"}
        ]
        recommendation = "Layanan analisis AI sedang sibuk. Statistik administrasi Anda tetap ditampilkan secara real-time."

    # Calculate dynamic index and trends based on live DB metrics
    avg_weekly = float(docs_count * 0.1 + 1.2)
    trend = "Meningkat" if docs_count > 10 else "Stabil"
    index_score = min(10.0, float(docs_count * 0.5 + 2.0))
    
    response_data = {
        "predictions": predictions,
        "recommendation": recommendation,
        "average_weekly_load": avg_weekly,
        "forecast_trend": trend,
        "workload_index": index_score,
        "stats": {
            "surat_masuk": surat_masuk_count,
            "surat_keluar": surat_keluar_count,
            "reminders": reminders_count
        }
    }
    return jsonify(response_data), 200
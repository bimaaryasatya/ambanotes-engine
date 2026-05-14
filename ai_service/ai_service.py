import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify
import requests
from common.config import Config
from common.logger import log_event
from common.jwt_utils import token_required
from common.db import docs_col

ai_bp = Blueprint('ai', __name__)


@ai_bp.route("/summarize", methods=["POST"])
@token_required
def summarize(current_user):
    """
    Summarize document text with Mistral AI
    ---
    tags:
      - AI
    security:
      - BearerAuth: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            text:
              type: string
              example: "Konten surat yang panjang..."
    responses:
      200:
        description: Summary generated successfully
      400:
        description: No text provided
      401:
        description: Unauthorized
      500:
        description: Error processing request
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    log_event("ai_service", f"Summarize request from: {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="AI_SUMMARIZE_START")
    try:
        data = request.json or {}
        text = data.get("text", "")

        if not text:
            return jsonify({"error": "No text provided"}), 400

        prompt = f"Tolong buatkan ringkasan singkat dan padat dari teks dokumen berikut ini:\n\n{text}"

        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {Config.MISTRAL_API_KEY}"},
            json={
                "model": "mistral-small",
                "messages": [{"role": "user", "content": prompt}]
            }
        )

        response.raise_for_status()
        result = response.json()
        summary = result['choices'][0]['message']['content']

        log_event("ai_service", "Summary generated successfully",
                  user_id=user_id, org_id=org_id, action="AI_SUMMARIZE_SUCCESS")
        return jsonify({"summary": summary}), 200

    except Exception as e:
        log_event("ai_service", f"Summarization error: {str(e)}",
                  user_id=user_id, org_id=org_id, action="AI_SUMMARIZE_FAILED", metadata={"error": str(e)})
        return jsonify({"error": str(e)}), 500


@ai_bp.route("/chat", methods=["POST"])
@token_required
def chat(current_user):
    """
    Chatbot endpoint using Mistral AI (Specific Context)
    ---
    tags:
      - AI
    security:
      - BearerAuth: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            message:
              type: string
              example: "Apa isi dari surat ini?"
            context:
              type: string
              example: "Isi teks surat..."
    responses:
      200:
        description: Chat response generated
      401:
        description: Unauthorized
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    log_event("ai_service", f"Chat request from: {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="AI_CHAT_START")
    try:
        data = request.json or {}
        user_message = data.get("message", "")
        context = data.get("context", "")

        messages = []
        if context:
            messages.append({"role": "system", "content": f"Anda adalah asisten cerdas AmbaNotes. Gunakan konteks dokumen berikut untuk menjawab: {context}"})

        messages.append({"role": "user", "content": user_message})

        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {Config.MISTRAL_API_KEY}"},
            json={
                "model": "mistral-small",
                "messages": messages
            }
        )

        response.raise_for_status()
        result = response.json()
        answer = result['choices'][0]['message']['content']

        log_event("ai_service", "Chat response generated",
                  user_id=user_id, org_id=org_id, action="AI_CHAT_SUCCESS")
        return jsonify({"answer": answer}), 200

    except Exception as e:
        log_event("ai_service", f"Chat error: {str(e)}",
                  user_id=user_id, org_id=org_id, action="AI_CHAT_FAILED", metadata={"error": str(e)})
        return jsonify({"error": str(e)}), 500


@ai_bp.route("/chat-global", methods=["POST"])
@token_required
def chat_global(current_user):
    """
    Organization-wide Chatbot (Reads all documents)
    ---
    tags:
      - AI
    security:
      - BearerAuth: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            message:
              type: string
              example: "Rangkum semua surat undangan yang ada."
    responses:
      200:
        description: Chat response generated based on all documents
      401:
        description: Unauthorized
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    log_event("ai_service", f"Global Chat request from: {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="AI_CHAT_GLOBAL_START")
    
    try:
        data = request.json or {}
        user_message = data.get("message", "")

        if not user_message:
            return jsonify({"error": "Message is required"}), 400

        # Fetch all documents for this organization
        docs = list(docs_col.find({"org_id": org_id}))
        
        if not docs:
            return jsonify({"answer": "Organisasi Anda belum memiliki dokumen untuk dianalisis."}), 200

        # Build global context
        global_context = "Berikut adalah daftar dokumen yang tersedia di organisasi Anda:\n\n"
        for i, doc in enumerate(docs):
            filename = doc.get('filename', 'Tanpa Nama')
            content = doc.get('content', '')
            global_context += f"Dokumen {i+1} ({filename}):\n{content}\n---\n"

        # Limit context size to avoid token issues (simple truncation for now)
        if len(global_context) > 15000:
            global_context = global_context[:15000] + "... [Konteks dipotong karena terlalu panjang]"

        messages = [
            {
                "role": "system", 
                "content": (
                    "Anda adalah asisten cerdas AmbaNotes. Tugas Anda adalah membantu pengguna mengelola "
                    "dan menganalisis seluruh dokumen di organisasi mereka. "
                    "Berikut adalah konteks dari seluruh dokumen yang ada:\n\n"
                    f"{global_context}"
                )
            },
            {"role": "user", "content": user_message}
        ]

        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {Config.MISTRAL_API_KEY}"},
            json={
                "model": "mistral-small",
                "messages": messages
            }
        )

        response.raise_for_status()
        result = response.json()
        answer = result['choices'][0]['message']['content']

        log_event("ai_service", "Global Chat response generated",
                  user_id=user_id, org_id=org_id, action="AI_CHAT_GLOBAL_SUCCESS")
        
        return jsonify({"answer": answer}), 200

    except Exception as e:
        log_event("ai_service", f"Global Chat error: {str(e)}",
                  user_id=user_id, org_id=org_id, action="AI_CHAT_GLOBAL_FAILED", metadata={"error": str(e)})
        return jsonify({"error": str(e)}), 500

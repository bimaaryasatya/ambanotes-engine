import os
import sys
import re
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify
import requests
from datetime import datetime
from common.config import Config
from common.logger import log_event
from common.jwt_utils import token_required
from common.db import docs_col, reminders_col, chats_col
def _call_mistral(prompt, system_instruction=None, history=None):
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    
    if history:
        for msg in history:
            role = "user" if msg.get("sender") == "user" else "assistant"
            content = msg.get("content", "")
            messages.append({"role": role, "content": content})

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

ai_bp = Blueprint('ai', __name__)


@ai_bp.route("/summarize", methods=["POST"])
@token_required
def summarize(current_user):
    """
    Summarize Document Text
    ---
    tags:
      - AI
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
            - text
          properties:
            text:
              type: string
              example: "Isi dokumen surat yang panjang..."
    responses:
      200:
        description: Summary generated successfully
      400:
        description: No text provided
      401:
        description: Unauthorized
      500:
        description: AI processing error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    log_event("ai_service", f"Summarize request from: {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="AI_SUMMARIZE_START")
    try:
        data = request.get_json(force=True, silent=True) or {}
        text = data.get("text", "")

        if not text:
            return jsonify({"error": "No text provided"}), 400

        prompt = f"Tolong buatkan ringkasan singkat dan padat dari teks dokumen berikut ini:\n\n{text}"
        summary = _call_mistral(prompt)

        log_event("ai_service", "Summary generated successfully",
                  user_id=user_id, org_id=org_id, action="AI_SUMMARIZE_SUCCESS")
        return jsonify({"summary": summary}), 200

    except Exception as e:
        log_event("ai_service", f"Summarization error: {str(e)}",
                  user_id=user_id, org_id=org_id, action="AI_SUMMARIZE_FAILED", metadata={"error": str(e)}, severity="error")
        return jsonify({"error": "Failed to summarize text"}), 500


@ai_bp.route("/chat", methods=["POST"])
@token_required
def chat(current_user):
    """
    Contextual Chatbot (Single Document)
    ---
    tags:
      - AI
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
            - message
          properties:
            message:
              type: string
              example: "Apa isi dari surat ini?"
            context:
              type: string
              example: "Isi teks surat sebagai konteks..."
            doc_id:
              type: string
              example: "doc-uuid-here"
            history:
              type: array
              items:
                type: object
              example: [{"sender": "user", "content": "hello"}]
    responses:
      200:
        description: Chat response generated
      401:
        description: Unauthorized
      500:
        description: AI processing error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    log_event("ai_service", f"Chat request from: {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="AI_CHAT_START")
    try:
        data = request.get_json(force=True, silent=True) or {}
        user_message = data.get("message", "")
        context = data.get("context", "")
        history = data.get("history", []) or []
        doc_id = data.get("doc_id")

        if doc_id and not history:
            existing_chat = chats_col.find_one({"user_id": user_id, "doc_id": doc_id})
            if existing_chat:
                history = existing_chat.get("chat_json", [])

        system_instruction = f"Anda adalah asisten cerdas AmbaNotes. Gunakan konteks dokumen berikut untuk menjawab: {context}" if context else "Anda adalah asisten cerdas AmbaNotes."
        answer = _call_mistral(user_message, system_instruction=system_instruction, history=history)

        updated_history = list(history) + [
            {"sender": "user", "content": user_message},
            {"sender": "assistant", "content": answer}
        ]

        if doc_id:
            chats_col.update_one(
                {"user_id": user_id, "doc_id": doc_id},
                {"$set": {
                    "chat_json": updated_history,
                    "updated_at": datetime.utcnow()
                }},
                upsert=True
            )

        log_event("ai_service", "Chat response generated",
                  user_id=user_id, org_id=org_id, action="AI_CHAT_SUCCESS",
                  audience="owner" if current_user.get("role") == "owner" else "user",
                  visibility="app",
                  severity="info")
        return jsonify({"answer": answer, "history": updated_history}), 200

    except Exception as e:
        log_event("ai_service", f"Chat error: {str(e)}",
                  user_id=user_id, org_id=org_id, action="AI_CHAT_FAILED", metadata={"error": str(e)}, severity="error")
        return jsonify({"error": "Failed to generate chat response"}), 500


@ai_bp.route("/chats", methods=["GET"])
@token_required
def list_chats(current_user):
    """
    List Chat Histories for the User
    ---
    tags:
      - AI
    produces:
      - application/json
    security:
      - BearerAuth: []
    responses:
      200:
        description: List of user chat sessions
      401:
        description: Unauthorized
      500:
        description: Database or processing error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")
    log_event("ai_service", f"List chats request from: {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="AI_LIST_CHATS_START")
    try:
        chats = list(chats_col.find({"user_id": user_id}).sort("updated_at", -1))
        result = []
        for chat in chats:
            doc_id = chat.get("doc_id")
            filename = "Unknown Document"
            if doc_id:
                doc = docs_col.find_one({"doc_id": doc_id})
                if doc:
                    filename = doc.get("filename", filename)
            result.append({
                "doc_id": doc_id,
                "filename": filename,
                "chat_json": chat.get("chat_json", []),
                "updated_at": chat.get("updated_at").isoformat() if chat.get("updated_at") else None
            })
        log_event("ai_service", "List chats success", user_id=user_id, org_id=org_id, action="AI_LIST_CHATS_SUCCESS")
        return jsonify(result), 200
    except Exception as e:
        log_event("ai_service", f"List chats error: {str(e)}", user_id=user_id, org_id=org_id, action="AI_LIST_CHATS_FAILED")
        return jsonify({"error": "An internal error has occurred."}), 500


@ai_bp.route("/chat/<doc_id>", methods=["GET"])
@token_required
def get_chat_detail(current_user, doc_id):
    """
    Get Chat History for a Specific Document
    ---
    tags:
      - AI
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: doc_id
        in: path
        type: string
        required: true
        description: "The document ID of the chat"
    responses:
      200:
        description: Chat history retrieved successfully
      401:
        description: Unauthorized
      500:
        description: Database or processing error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")
    log_event("ai_service", f"Get chat detail request for doc_id: {doc_id} from: {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="AI_GET_CHAT_DETAIL_START")
    try:
        chat = chats_col.find_one({"user_id": user_id, "doc_id": doc_id})
        if not chat:
            return jsonify({"chat_json": [], "message": "No chat history found for this document"}), 200

        filename = "Unknown Document"
        doc = docs_col.find_one({"doc_id": doc_id})
        if doc:
            filename = doc.get("filename", filename)

        result = {
            "doc_id": doc_id,
            "filename": filename,
            "chat_json": chat.get("chat_json", []),
            "updated_at": chat.get("updated_at").isoformat() if chat.get("updated_at") else None
        }
        log_event("ai_service", "Get chat detail success", user_id=user_id, org_id=org_id, action="AI_GET_CHAT_DETAIL_SUCCESS")
        return jsonify(result), 200
    except Exception as e:
        log_event("ai_service", f"Get chat detail error: {str(e)}", user_id=user_id, org_id=org_id, action="AI_GET_CHAT_DETAIL_FAILED")
        return jsonify({"error": "An internal error occurred"}), 500


@ai_bp.route("/chat/<doc_id>", methods=["DELETE"])
@token_required
def delete_chat_detail(current_user, doc_id):
    """
    Delete Chat History for a Specific Document
    ---
    tags:
      - AI
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: doc_id
        in: path
        type: string
        required: true
        description: "The document ID of the chat to delete"
    responses:
      200:
        description: Chat history deleted successfully
      404:
        description: Chat history not found
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    log_event(
        "ai_service",
        f"Delete chat request for doc_id: {doc_id} from: {current_user.get('username')}",
        user_id=user_id,
        org_id=org_id,
        action="AI_DELETE_CHAT_START",
        metadata={"doc_id": doc_id},
    )

    try:
        result = chats_col.delete_one({"user_id": user_id, "doc_id": doc_id})

        if result.deleted_count == 0:
            log_event(
                "ai_service",
                f"Chat history not found for delete: {doc_id}",
                user_id=user_id,
                org_id=org_id,
                action="AI_DELETE_CHAT_NOT_FOUND",
                metadata={"doc_id": doc_id},
            )
            return jsonify({"error": "Chat history not found"}), 404

        log_event(
            "ai_service",
            f"Chat history deleted for doc_id: {doc_id}",
            user_id=user_id,
            org_id=org_id,
            action="AI_DELETE_CHAT_SUCCESS",
            metadata={"doc_id": doc_id},
            audience="owner" if current_user.get("role") == "owner" else "user",
            visibility="app",
            severity="info",
        )
        return jsonify({"message": "Chat history deleted"}), 200
    except Exception as e:
        log_event(
            "ai_service",
            f"Delete chat error: {str(e)}",
            user_id=user_id,
            org_id=org_id,
            action="AI_DELETE_CHAT_FAILED",
            metadata={"doc_id": doc_id, "error": str(e)},
        )
        return jsonify({"error": "An internal error occurred"}), 500



@ai_bp.route("/chat-global", methods=["POST"])
@token_required
def chat_global(current_user):
    """
    Organization-wide Chatbot with Citations
    ---
    tags:
      - AI
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
            - message
          properties:
            message:
              type: string
              example: "Rangkum semua surat undangan yang ada."
    responses:
      200:
        description: Chat response with document references
      400:
        description: Message is required
      401:
        description: Unauthorized
      500:
        description: AI processing error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    log_event("ai_service", f"Global Chat request from: {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="AI_CHAT_GLOBAL_START")
    
    try:
        data = request.get_json(force=True, silent=True) or {}
        user_message = data.get("message", "")

        if not user_message:
            return jsonify({"error": "Message is required"}), 400

        # Fetch all documents for this organization
        docs = list(docs_col.find({"org_id": org_id}))
        
        if not docs:
            return jsonify({
                "answer": "Organisasi Anda belum memiliki dokumen untuk dianalisis.",
                "references": []
            }), 200

        # Build global context with IDs for citations
        global_context = "Berikut adalah daftar dokumen yang tersedia di organisasi Anda:\n\n"
        for i, doc in enumerate(docs):
            d_id = doc.get('doc_id')
            filename = doc.get('filename', 'Tanpa Nama')
            content = doc.get('content', '')
            global_context += f"DOKUMEN_ID: {d_id}\nFILE: {filename}\nISI: {content}\n---\n"

        # Limit context size
        if len(global_context) > 15000:
            global_context = global_context[:15000] + "... [Konteks dipotong]"

        system_instruction = (
            "Anda adalah asisten cerdas AmbaNotes. Tugas Anda adalah membantu pengguna mengelola "
            "dan menganalisis seluruh dokumen di organisasi mereka.\n\n"
            "ATURAN PENTING:\n"
            "1. Jika Anda mengambil informasi dari dokumen tertentu, Anda WAJIB mencantumkan ID dokumen tersebut "
            "di akhir kalimat yang relevan menggunakan format [[DOKUMEN_ID]].\n"
            "   Contoh: 'Rapat akan diadakan pada tanggal 20 Mei [[abc-123]].'\n"
            "2. Gunakan informasi HANYA dari dokumen yang disediakan di atas.\n"
            "3. Jika jawaban melibatkan banyak dokumen, cantumkan semua ID yang relevan.\n\n"
            f"KONTEKS DOKUMEN:\n{global_context}"
        )
        history = data.get("history", [])
        answer = _call_mistral(user_message, system_instruction=system_instruction, history=history)

        # Extract citations [[...]] using Regex
        citation_ids = re.findall(r"\[\[(.*?)\]\]", answer)
        references = []
        seen_ids = set()
        
        for cid in citation_ids:
            cid = cid.strip()
            if cid not in seen_ids:
                # Match against our fetched docs
                match = next((d for d in docs if d['doc_id'] == cid), None)
                if match:
                    references.append({
                        "doc_id": match['doc_id'],
                        "filename": match['filename'],
                        "classification": match.get('classification', {}).get('label_name', 'Unknown')
                    })
                    seen_ids.add(cid)

        log_event("ai_service", "Global Chat response with citations generated",
                  user_id=user_id, org_id=org_id, action="AI_CHAT_GLOBAL_SUCCESS", 
                  metadata={"ref_count": len(references)})
        
        return jsonify({
            "answer": answer,
            "references": references
        }), 200

    except Exception as e:
        log_event("ai_service", f"Global Chat error: {str(e)}",
                  user_id=user_id, org_id=org_id, action="AI_CHAT_GLOBAL_FAILED", metadata={"error": str(e)}, severity="error")
        return jsonify({"error": "Failed to generate global chat response"}), 500


@ai_bp.route("/extract-tasks", methods=["POST"])
@token_required
def extract_tasks(current_user):
    """
    Extract Tasks & Agenda from Letter
    ---
    tags:
      - AI
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
            - text
          properties:
            text:
              type: string
              example: "Rapat akan diadakan pada tanggal 20 Mei 2026 pukul 10:00 di Aula Utama."
    responses:
      200:
        description: Array of extracted tasks (JSON)
      400:
        description: No text provided
      401:
        description: Unauthorized
      500:
        description: AI processing error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    try:
        data = request.get_json(force=True, silent=True) or {}
        text = data.get("text", "")
        if not text:
            return jsonify({"error": "No text provided"}), 400

        prompt = (
            "Ekstrak daftar tugas, agenda, atau kegiatan penting dari teks surat berikut.\n"
            "Hasilkan output HANYA dalam format JSON valid (array of objects) seperti contoh ini:\n"
            "[\n"
            "  {\"task\": \"Rapat Koordinasi\", \"date\": \"2026-05-20\", \"time\": \"10:00\", \"location\": \"Ruang Aula\"}\n"
            "]\n"
            "Jika tidak ada kegiatan sama sekali, kembalikan array kosong [].\n\n"
            f"Teks Surat:\n{text}"
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
        content = response.json()['choices'][0]['message']['content']
        
        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        if json_match:
            tasks = json.loads(json_match.group())
        else:
            tasks = []

        log_event("ai_service", "Tasks extracted successfully", user_id=user_id, org_id=org_id, action="AI_EXTRACT_TASKS_SUCCESS")
        return jsonify(tasks), 200

    except Exception as e:
        log_event("ai_service", f"Task extraction error: {str(e)}", user_id=user_id, org_id=org_id, action="AI_EXTRACT_TASKS_FAILED", severity="error")
        return jsonify({"error": "Failed to extract tasks"}), 500


@ai_bp.route("/generate-reply", methods=["POST"])
@token_required
def generate_reply(current_user):
    """
    Generate 3 Formal Reply Drafts (Accept, Decline, Neutral)
    ---
    tags:
      - AI
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
            - text
          properties:
            text:
              type: string
              example: "Dengan hormat, kami mengundang Bapak/Ibu untuk menghadiri rapat..."
    responses:
      200:
        description: JSON with accept, decline, neutral drafts
      400:
        description: No text provided
      401:
        description: Unauthorized
      500:
        description: AI processing error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    try:
        data = request.get_json(force=True, silent=True) or {}
        text = data.get("text", "")
        if not text:
            return jsonify({"error": "No text provided"}), 400

        prompt = (
            "Buatkan 3 opsi draf balasan surat formal (Setuju/Menerima, Menolak dengan Sopan, dan Netral/Menanyakan Detail) "
            "berdasarkan isi surat berikut. Gunakan Bahasa Indonesia yang sangat formal dan profesional.\n"
            "Hasilkan output HANYA dalam format JSON valid seperti ini:\n"
            "{\n"
            "  \"accept\": \"...\",\n"
            "  \"decline\": \"...\",\n"
            "  \"neutral\": \"...\"\n"
            "}\n\n"
            f"Isi Surat:\n{text}"
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
        content = response.json()['choices'][0]['message']['content']
        
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            replies = json.loads(json_match.group())
        else:
            replies = {"error": "Format draf tidak valid"}

        log_event("ai_service", "Reply drafts generated", user_id=user_id, org_id=org_id, action="AI_GENERATE_REPLY_SUCCESS")
        return jsonify(replies), 200

    except Exception as e:
        log_event("ai_service", f"Reply generation error: {str(e)}", user_id=user_id, org_id=org_id, action="AI_GENERATE_REPLY_FAILED", severity="error")
        return jsonify({"error": "Failed to generate reply drafts"}), 500


@ai_bp.route("/translate", methods=["POST"])
@token_required
def translate_text(current_user):
    """
    Translate Text to Formal Indonesian
    ---
    tags:
      - AI
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
            - text
          properties:
            text:
              type: string
              example: "We would like to invite you to the coordination meeting."
    responses:
      200:
        description: Translated text in formal Indonesian
      400:
        description: No text provided
      401:
        description: Unauthorized
      500:
        description: AI processing error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    try:
        data = request.get_json(force=True, silent=True) or {}
        text = data.get("text", "")
        if not text:
            return jsonify({"error": "No text provided"}), 400

        prompt = (
            "Terjemahkan teks berikut ke dalam Bahasa Indonesia formal yang sangat akurat dan profesional. "
            "Gunakan gaya bahasa kedinasan/resmi.\n\n"
            f"Teks: {text}"
        )

        translated = _call_mistral(prompt)

        log_event("ai_service", "Translation successful", user_id=user_id, org_id=org_id, action="AI_TRANSLATE_SUCCESS")
        return jsonify({"translated_text": translated}), 200

    except Exception as e:
        log_event("ai_service", f"Translation error: {str(e)}", user_id=user_id, org_id=org_id, action="AI_TRANSLATE_FAILED", severity="error")
        return jsonify({"error": "Failed to translate text"}), 500


@ai_bp.route("/suggest-disposition", methods=["POST"])
@token_required
def suggest_disposition(current_user):
    """
    Suggest Department for Incoming Letter (Smart Disposition)
    ---
    tags:
      - AI
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
            - text
            - delegations
          properties:
            text:
              type: string
              example: "Permohonan perbaikan jalan raya di Kecamatan Sumpiuh."
            delegations:
              type: array
              items:
                type: string
              example: ["Dinas Pekerjaan Umum", "Dinas Sosial", "Dinas Kesehatan"]
    responses:
      200:
        description: JSON with suggested_delegation and reason
      400:
        description: Text and delegations list are required
      401:
        description: Unauthorized
      500:
        description: AI processing error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    try:
        data = request.get_json(force=True, silent=True) or {}
        text = data.get("text", "")
        delegations = data.get("delegations", []) 

        if not text or not delegations:
            return jsonify({"error": "Text and delegations list are required"}), 400

        prompt = (
            f"Berdasarkan teks surat di bawah ini, pilih satu unit/departemen yang paling tepat untuk menangani surat tersebut "
            f"dari daftar berikut: {', '.join(delegations)}.\n"
            "Berikan jawaban dalam format JSON valid:\n"
            "{\n"
            "  \"suggested_delegation\": \"...\",\n"
            "  \"reason\": \"...\"\n"
            "}\n\n"
            f"Teks Surat:\n{text}"
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
        content = response.json()['choices'][0]['message']['content']
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        suggestion = json.loads(json_match.group()) if json_match else {"error": "No suggestion generated"}

        log_event("ai_service", "Disposition suggestion generated", user_id=user_id, org_id=org_id, action="AI_DISPOSITION_SUCCESS")
        return jsonify(suggestion), 200

    except Exception as e:
        log_event("ai_service", f"Disposition suggestion error: {str(e)}", user_id=user_id, org_id=org_id, action="AI_SUGGEST_DISPOSITION_FAILED", severity="error")
        return jsonify({"error": "Failed to generate disposition suggestion"}), 500


@ai_bp.route("/redact-sensitive", methods=["POST"])
@token_required
def redact_sensitive(current_user):
    """
    Redact Sensitive Personal Data (NIK, Phone, Address)
    ---
    tags:
      - AI
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
            - text
          properties:
            text:
              type: string
              example: "Nama: Budi, NIK: 3302041234567890, HP: 081234567890, Alamat: Jl. Merdeka No.1"
    responses:
      200:
        description: Text with sensitive data replaced by [SENSORS]
      400:
        description: No text provided
      401:
        description: Unauthorized
      500:
        description: AI processing error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    try:
        data = request.get_json(force=True, silent=True) or {}
        text = data.get("text", "")
        if not text:
            return jsonify({"error": "No text provided"}), 400

        prompt = (
            "Identifikasi dan sensor (ganti dengan [SENSORS]) semua informasi sensitif di bawah ini seperti: "
            "NIK (16 digit), Nomor HP, Alamat Rumah Lengkap, dan Nomor Rekening.\n"
            "Jangan sensor nama instansi atau jabatan resmi.\n\n"
            f"Teks:\n{text}"
        )

        redacted = _call_mistral(prompt)

        log_event("ai_service", "Sensitive data redacted", user_id=user_id, org_id=org_id, action="AI_REDACT_SUCCESS")
        return jsonify({"redacted_text": redacted}), 200

    except Exception as e:
        log_event("ai_service", f"Sensitive data redaction error: {str(e)}", user_id=user_id, org_id=org_id, action="AI_REDACT_FAILED", severity="error")
        return jsonify({"error": "Failed to redact sensitive data"}), 500


@ai_bp.route("/semantic-search", methods=["POST"])
@token_required
def semantic_search(current_user):
    """
    Semantic Search (Find Documents by Meaning)
    ---
    tags:
      - AI
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
            - query
          properties:
            query:
              type: string
              example: "surat tentang anggaran belanja kantor"
    responses:
      200:
        description: Array of relevant documents (doc_id, filename)
      400:
        description: Query is required
      401:
        description: Unauthorized
      500:
        description: AI processing error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    try:
        data = request.get_json(force=True, silent=True) or {}
        query = data.get("query", "")
        if not query:
            return jsonify({"error": "Query is required"}), 400

        # Fetch titles and snippets for all organization docs
        docs = list(docs_col.find({"org_id": org_id}, {"doc_id": 1, "filename": 1, "content": 1}))
        if not docs:
            return jsonify([]), 200

        doc_list = []
        for d in docs:
            snippet = d.get('content', '')[:200].replace('\n', ' ')
            doc_list.append(f"ID: {d['doc_id']} | File: {d['filename']} | Snippet: {snippet}")

        prompt = (
            f"Berdasarkan daftar dokumen berikut, pilih maksimal 5 dokumen yang paling relevan dengan pertanyaan/kueri: '{query}'.\n"
            "Pilih berdasarkan makna, bukan hanya kata kunci.\n"
            f"Daftar Dokumen:\n{json.dumps(doc_list)}\n\n"
            "Hasilkan output HANYA dalam format JSON valid (array of document IDs):\n"
            "[\"id1\", \"id2\", ...]\n"
            "Jika tidak ada yang relevan, kembalikan []."
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
        content = response.json()['choices'][0]['message']['content']
        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        relevant_ids = json.loads(json_match.group()) if json_match else []

        # Fetch full metadata for results
        results = []
        for rid in relevant_ids:
            match = next((d for d in docs if str(d['doc_id']) == str(rid)), None)
            if match:
                results.append({
                    "doc_id": match['doc_id'],
                    "filename": match['filename']
                })

        log_event("ai_service", "Semantic search completed", user_id=user_id, org_id=org_id, action="AI_SEMANTIC_SEARCH_SUCCESS")
        return jsonify(results), 200

    except Exception as e:
        log_event("ai_service", f"Semantic search error: {str(e)}", user_id=user_id, org_id=org_id, action="AI_SEMANTIC_SEARCH_FAILED", severity="error")
        return jsonify({"error": "Failed to perform semantic search"}), 500


@ai_bp.route("/voice-intent", methods=["POST"])
@token_required
def voice_intent(current_user):
    """
    Voice Intent Extraction (Speech to Action)
    ---
    tags:
      - AI
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
            - text
          properties:
            text:
              type: string
              example: "Buatkan pengingat rapat besok jam 10 pagi di aula"
    responses:
      200:
        description: JSON with intent and extracted params
      400:
        description: No text provided
      401:
        description: Unauthorized
      500:
        description: AI processing error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    try:
        data = request.get_json(force=True, silent=True) or {}
        text = data.get("text", "")
        if not text:
            return jsonify({"error": "No text provided"}), 400

        prompt = (
            f"Analisis teks perintah suara berikut: '{text}'.\n"
            "Tentukan niat (intent) pengguna dan ekstrak data penting.\n"
            "Intent yang didukung: 'create_reminder', 'generate_letter', 'find_document'.\n"
            "Hasilkan output HANYA dalam format JSON valid:\n"
            "{\n"
            "  \"intent\": \"...\",\n"
            "  \"params\": { ... data spesifik seperti task, date, doc_name dll ... }\n"
            "}\n\n"
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
        content = response.json()['choices'][0]['message']['content']
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        intent_data = json.loads(json_match.group()) if json_match else {"intent": "unknown"}

        log_event("ai_service", "Voice intent extracted", user_id=user_id, org_id=org_id, action="AI_VOICE_INTENT_SUCCESS")
        return jsonify(intent_data), 200

    except Exception as e:
        log_event("ai_service", f"Voice intent extraction error: {str(e)}", user_id=user_id, org_id=org_id, action="AI_VOICE_INTENT_FAILED", severity="error")
        return jsonify({"error": "Failed to extract voice intent"}), 500


@ai_bp.route("/analyze-workflow", methods=["POST"])
@token_required
def analyze_workflow(current_user):
    """
    AI Workflow Analysis & Conflict Detection
    ---
    tags:
      - AI
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
            - text
          properties:
            text:
              type: string
              example: "Surat tugas Bima ke Jakarta tanggal 20 Mei 2026."
    responses:
      200:
        description: Workflow analysis results with conflicts and suggestions
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    try:
        data = request.get_json(force=True, silent=True) or {}
        text = data.get("text", "")
        
        # 1. Fetch existing reminders/tasks for context
        existing_tasks = list(reminders_col.find({"org_id": org_id}).sort("date", -1).limit(10))
        context_tasks = ""
        for t in existing_tasks:
            context_tasks += f"- {t['task']} pada {t['date']} {t.get('time', '')}\n"

        prompt = (
            "Anda adalah AI Auditor AmbaNotes. Tugas Anda adalah menganalisis surat baru dan mengecek konflik "
            "dengan agenda yang sudah ada, serta memberikan saran workflow otomatis.\n\n"
            f"AGENDA EKSISTING:\n{context_tasks}\n"
            f"SURAT BARU:\n{text}\n\n"
            "Hasilkan output HANYA dalam format JSON valid:\n"
            "{\n"
            "  \"conflicts\": [\"... list konflik jika ada ...\"],\n"
            "  \"automation_suggestions\": [\n"
            "    {\"action\": \"create_calendar_event\", \"data\": {...}},\n"
            "    {\"action\": \"send_whatsapp_reminder\", \"target\": \"...\"}\n"
            "  ],\n"
            "  \"risk_score\": 0.0 to 1.0\n"
            "}"
        )

        content = _call_mistral(prompt)
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        analysis = json.loads(json_match.group()) if json_match else {"error": "Analysis failed"}

        return jsonify(analysis), 200
    except Exception as e:
        log_event("ai_service", f"Workflow analysis error: {str(e)}", user_id=user_id, org_id=org_id, action="AI_WORKFLOW_ANALYSIS_FAILED", severity="error")
        return jsonify({"error": "Failed to analyze workflow"}), 500


@ai_bp.route("/extract-budget", methods=["POST"])
@token_required
def extract_budget(current_user):
    """
    Extract Monetary Values & Budget Purposes
    ---
    tags:
      - AI
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
            - text
          properties:
            text:
              type: string
              example: "Anggaran perbaikan jalan sebesar Rp 500.000.000 untuk tahun 2026."
    responses:
      200:
        description: Extracted budget data
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    try:
        data = request.get_json(force=True, silent=True) or {}
        text = data.get("text", "")

        prompt = (
            "Ekstrak semua informasi keuangan dari teks berikut.\n"
            "Hasilkan output HANYA dalam format JSON valid (array of objects):\n"
            "[\n"
            "  {\"amount\": 500000, \"currency\": \"IDR\", \"purpose\": \"...\", \"year\": \"...\"}\n"
            "]\n"
            f"Teks:\n{text}"
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
        content = response.json()['choices'][0]['message']['content']
        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        budget_data = json.loads(json_match.group()) if json_match else []

        return jsonify(budget_data), 200
    except Exception as e:
        log_event("ai_service", f"Budget extraction error: {str(e)}", user_id=user_id, org_id=org_id, action="AI_EXTRACT_BUDGET_FAILED", severity="error")
        return jsonify({"error": "Failed to extract budget data"}), 500


@ai_bp.route("/analyze-priority", methods=["POST"])
@token_required
def analyze_priority(current_user):
    """
    Analyze Document Priority, Sentiment, and Auto-Tags
    ---
    tags:
      - AI
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
            - text
          properties:
            text:
              type: string
              example: "URGENT: Perbaikan jembatan ambruk harus selesai dalam 2 hari!"
    responses:
      200:
        description: Priority, Sentiment, and Tags analysis
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    try:
        data = request.get_json(force=True, silent=True) or {}
        text = data.get("text", "")

        prompt = (
            "Analisis teks surat berikut secara mendalam.\n"
            "Tentukan:\n"
            "1. Urgency (High/Medium/Low)\n"
            "2. Sentiment (Positive/Neutral/Negative/Urgent)\n"
            "3. Tags (Maksimal 5 hashtag kategori yang relevan)\n"
            "4. Summary_Short (Maksimal 10 kata)\n\n"
            "Hasilkan output HANYA dalam format JSON valid:\n"
            "{\n"
            "  \"urgency\": \"...\",\n"
            "  \"sentiment\": \"...\",\n"
            "  \"tags\": [\"#tag1\", \"#tag2\"],\n"
            "  \"brief_summary\": \"...\"\n"
            "}\n\n"
            f"Teks:\n{text}"
        )

        content = _call_mistral(prompt)
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        analysis = json.loads(json_match.group()) if json_match else {"error": "Analysis failed"}

        log_event("ai_service", "Priority analysis completed", user_id=user_id, org_id=org_id, action="AI_PRIORITY_SUCCESS")
        return jsonify(analysis), 200
    except Exception as e:
        log_event("ai_service", f"Priority analysis error: {str(e)}", user_id=user_id, org_id=org_id, action="AI_PRIORITY_FAILED", severity="error")
        return jsonify({"error": "Failed to analyze document priority"}), 500

import os
import sys
import re

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request, send_file
from common.logger import log_event
from common.jwt_utils import token_required, role_required

import requests
from common.db import docs_col, users_col, delegations_col
from bson.objectid import ObjectId
import uuid
import datetime
import base64
from io import BytesIO
from common.google_drive_client import (
    upload_file_to_google_drive,
    download_file_from_google_drive,
    delete_file_from_google_drive
)

from common.config import Config

document_bp = Blueprint('document', __name__)

# Use central configuration
GATEWAY_URL = Config.GATEWAY_URL

def _get_auth_header():
    """Ambil Authorization header dari request yang sedang aktif untuk diteruskan ke service internal."""
    return {"Authorization": request.headers.get("Authorization", "")}


def process_ai_pipeline(text, headers=None):
    """Fungsi helper untuk menjalankan Klasifikasi dan NER (meneruskan token auth)."""
    if headers is None:
        headers = _get_auth_header()
    try:
        class_res = requests.post(f"{GATEWAY_URL}/classification/predict", json={"text": text}, headers=headers)
        classification = class_res.json() if class_res.status_code == 200 else {"label": "Unknown"}

        ner_res = requests.post(f"{GATEWAY_URL}/ner/extract", json={"text": text}, headers=headers)
        entities = ner_res.json() if ner_res.status_code == 200 else {}

        return classification, entities
    except Exception as e:
        log_event("document_service", f"AI Pipeline error: {str(e)}", action="AI_PIPELINE_ERROR", metadata={"error": str(e)})
        return {"label": "Error"}, {}


_delegation_cache = {}

def _get_delegation_name_cached(delegation_id, org_id):
    if not delegation_id or delegation_id == "general":
        return "General"
    cache_key = f"{org_id}:{delegation_id}"
    if cache_key not in _delegation_cache:
        delegation = None
        try:
            delegation = delegations_col.find_one({"_id": ObjectId(delegation_id), "org_id": org_id})
        except Exception:
            delegation = delegations_col.find_one({"_id": delegation_id, "org_id": org_id})
        _delegation_cache[cache_key] = delegation.get("name") if delegation else "General"
    return _delegation_cache[cache_key]

def _serialize_doc(doc):
    doc.pop("_id", None)
    delegation_id = doc.get("delegation_id") or "general"
    doc["delegation_id"] = delegation_id
    doc["delegation_name"] = _get_delegation_name_cached(delegation_id, doc.get("org_id"))
    if not doc.get("title"):
        doc["title"] = doc.get("filename")
    return doc


def generate_document_title(extracted_text, filename):
    """
    Menghasilkan judul pendek (3-6 kata) berdasarkan isi surat untuk nama card surat.
    """
    if not extracted_text or not extracted_text.strip():
        return os.path.splitext(filename)[0]

    prompt = (
        "Tugas Anda: Buatlah satu judul/nama singkat yang sangat jelas dan formal (maksimal 5 kata) "
        "untuk dokumen/surat berdasarkan teks hasil OCR berikut ini. Judul ini akan digunakan sebagai nama card surat di aplikasi.\n"
        "Aturan:\n"
        "1. JANGAN gunakan tanda kutip, emoji, kata 'Judul:', atau penjelasan tambahan.\n"
        "2. Ambil inti perihal surat tersebut (misal: 'Undangan Rapat Koordinasi', 'Surat Perjanjian Kerja', 'Pengumuman Libur Bersama').\n"
        "3. Berikan langsung judulnya.\n\n"
        f"Teks Surat:\n{extracted_text}"
    )

    try:
        api_key = Config.MISTRAL_API_KEY
        if not api_key:
            return os.path.splitext(filename)[0]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "mistral-small-latest",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }

        response = requests.post("https://api.mistral.ai/v1/chat/completions", json=payload, headers=headers, timeout=5)
        if response.status_code == 200:
            title = response.json()["choices"][0]["message"]["content"].strip()
            title = re.sub(r'^["\'`*:]+|["\'`*:]+$', '', title).strip()
            return title
    except Exception as e:
        log_event("document_service", f"Gagal generate title via Mistral: {str(e)}", action="MISTRAL_TITLE_ERROR")

    return os.path.splitext(filename)[0]


def generate_security_suggestion(doc_data):
    """
    Menghasilkan saran keamanan dinamis bersih (tanpa emoji, bold markdown pada kata penting) menggunakan Mistral AI.
    """
    entities = doc_data.get("entities", {})
    classification = doc_data.get("classification", {})
    
    no_surat = entities.get("nomor_surat", "")
    kategori = classification.get("label", "Dokumen")
    perihal = entities.get("perihal", "")
    instansi = entities.get("organisasi_penerbit", "")
    
    prompt = (
        "Anda adalah asisten keamanan siber profesional untuk aplikasi manajemen surat AmbaNotes.\n"
        "Tugas Anda: Buatlah 1-2 kalimat saran keamanan yang ramah, profesional, dan meyakinkan dalam bahasa Indonesia.\n"
        "Instruksi Khusus:\n"
        "1. JANGAN gunakan emoji, emotikon, atau ikon dekoratif apa pun (seperti 🔒, 🤖, dll).\n"
        "2. Gunakan markdown cetak tebal (**teks**) HANYA pada informasi penting berikut (jika datanya ada):\n"
        "   - Nomor surat\n"
        "   - Kategori/klasifikasi\n"
        "   - Perihal/subjek surat\n"
        "   - Nama instansi/organisasi penerbit\n"
        "3. Jelaskan bahwa dokumen ini dideteksi penting/sensitif dan disarankan agar pengguna menghubungkan Google Drive untuk memindahkan berkas fisik asli dari server umum kami ke cloud pribadi mereka untuk keamanan penuh.\n\n"
        "Informasi Berkas:\n"
        f"- Kategori Berkas: {kategori}\n"
        f"- Nomor Surat: {no_surat if no_surat else 'tidak terdeteksi'}\n"
        f"- Perihal: {perihal if perihal else 'tidak terdeteksi'}\n"
        f"- Instansi/Penerbit: {instansi if instansi else 'tidak terdeteksi'}\n\n"
        "Berikan langsung kalimat sarannya tanpa kata pengantar atau penjelasan tambahan."
    )
    
    try:
        api_key = Config.MISTRAL_API_KEY
        if not api_key:
            return f"Dokumen Anda yang dikategorikan sebagai **{kategori}** terdeteksi penting. Silakan hubungkan Google Drive untuk memindahkan dokumen fisik dari server ke ruang penyimpanan pribadi Anda."
            
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "mistral-small-latest",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }
        
        response = requests.post("https://api.mistral.ai/v1/chat/completions", json=payload, headers=headers, timeout=5)
        if response.status_code == 200:
            suggestion = response.json()["choices"][0]["message"]["content"].strip()
            return suggestion
    except Exception as e:
        log_event("document_service", f"Gagal generate security suggestion via Mistral: {str(e)}", action="MISTRAL_SUGGESTION_ERROR")
        
    return f"Dokumen Anda yang dikategorikan sebagai **{kategori}** dideteksi memiliki tingkat privasi yang tinggi. Silakan hubungkan Google Drive untuk memindahkan dokumen fisik dari server ke ruang penyimpanan pribadi Anda."


@document_bp.route('/upload', methods=['POST'])
@token_required
def upload_document(current_user):
    """
    Upload and Process Image File (OCR -> Classify -> NER)
    ---
    tags:
      - Document
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    consumes:
      - multipart/form-data
    parameters:
      - name: file
        in: formData
        type: file
        required: true
        description: The image file to process through the full AI pipeline
    responses:
      201:
        description: File processed and data saved successfully
      400:
        description: No file provided
      401:
        description: Unauthorized - invalid or missing token
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")
    
    log_event("document_service", f"Upload started by user: {current_user.get('username')}", 
              user_id=user_id, org_id=org_id, action="DOC_UPLOAD_START")

    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']

    filename = file.filename
    mimetype = file.mimetype
    try:
        file_bytes = file.read()
    except Exception as e:
        return jsonify({"error": f"Failed to read file: {str(e)}"}), 400

    doc_id = uuid.uuid4().hex
    
    # 1. Create a placeholder document with "processing" status
    doc_data = {
        "doc_id": doc_id,
        "filename": filename,
        "title": os.path.splitext(filename)[0],
        "content": "Dokumen sedang diproses di server oleh pipeline AI...",
        "classification": {"label": "Processing", "label_name": "Processing"},
        "entities": {},
        "uploaded_at": datetime.datetime.utcnow(),
        "uploaded_by": user_id,
        "org_id": org_id,
        "delegation_id": "general",
        "google_drive": None,
        "mimetype": mimetype,
        "status": "processing"
    }

    docs_col.insert_one(doc_data)
    
    response_data = dict(doc_data)
    response_data.pop("_id", None)
    response_data["delegation_name"] = "General"
    response_data["security_suggestion"] = "Dokumen Anda sedang diproses oleh AI..."

    auth_header = _get_auth_header()

    # 2. Run the pipeline asynchronously in a background thread
    import threading

    def process_document_async():
        try:
            try:
                # Run OCR
                files_payload = {'file': (filename, BytesIO(file_bytes), mimetype)}
                ocr_res = requests.post(f"{GATEWAY_URL}/ocr/extract-text", files=files_payload, headers=auth_header)
                ocr_res.raise_for_status()
                extracted_text = ocr_res.json().get("text", "")
            except Exception as e:
                log_event("document_service", f"Async OCR failed for {doc_id}: {str(e)}", 
                          user_id=user_id, org_id=org_id, action="DOC_OCR_FAILED", metadata={"error": str(e)}, severity="error")
                docs_col.update_one(
                    {"doc_id": doc_id, "org_id": org_id},
                    {"$set": {"status": "error", "content": f"Gagal menjalankan OCR pada berkas: {str(e)}"}}
                )
                return

            # Run AI pipeline
            classification, entities = process_ai_pipeline(extracted_text, headers=auth_header)

            # Google Drive / Base64 upload
            google_drive_data = None
            file_data_b64 = None

            owner = users_col.find_one({
                "org_id": org_id,
                "role": "owner",
                "google_drive_connected": True
            })

            if owner:
                refresh_token = owner.get("google_oauth", {}).get("refresh_token")
                if refresh_token:
                    try:
                        google_drive_data = upload_file_to_google_drive(
                            file_stream=BytesIO(file_bytes),
                            filename=filename,
                            mimetype=mimetype,
                            refresh_token=refresh_token
                        )
                        log_event(
                            "document_service",
                            f"Async uploaded file {filename} to organization owner's Google Drive",
                            user_id=user_id,
                            org_id=org_id,
                            action="DOC_DRIVE_UPLOAD_SUCCESS"
                        )
                    except Exception as drive_err:
                        log_event(
                            "document_service",
                            f"Failed async upload to owner's Google Drive: {str(drive_err)}, falling back to local Base64",
                            user_id=user_id,
                            org_id=org_id,
                            action="DOC_DRIVE_UPLOAD_FAILED"
                        )
                        file_data_b64 = base64.b64encode(file_bytes).decode("utf-8")
                else:
                    file_data_b64 = base64.b64encode(file_bytes).decode("utf-8")
            else:
                file_data_b64 = base64.b64encode(file_bytes).decode("utf-8")

            title = generate_document_title(extracted_text, filename)
            
            update_doc = {
                "title": title,
                "content": extracted_text,
                "classification": classification,
                "entities": entities,
                "google_drive": google_drive_data,
                "status": "processed"
            }

            if file_data_b64:
                update_doc["file_data"] = file_data_b64

            if not google_drive_data:
                temp_doc_for_suggestion = {
                    "classification": classification,
                    "entities": entities
                }
                update_doc["security_suggestion"] = generate_security_suggestion(temp_doc_for_suggestion)
            else:
                update_doc["security_suggestion"] = None

            docs_col.update_one({"doc_id": doc_id, "org_id": org_id}, {"$set": update_doc})

            print(f"[ASYNC] Document {doc_id} ({filename}) processed successfully — status: processed")
            log_event("document_service", f"Async file processed and saved: {filename}", 
                      user_id=user_id, org_id=org_id, action="DOC_UPLOAD_SUCCESS", 
                      metadata={"doc_id": doc_id, "filename": filename},
                      audience="owner" if current_user.get("role") == "owner" else "user",
                      visibility="app",
                      severity="info")
        except Exception as e:
            print(f"[ASYNC] FATAL ERROR processing document {doc_id}: {e}")
            log_event("document_service", f"Async processing fatally failed for {doc_id}: {str(e)}", 
                      user_id=user_id, org_id=org_id, action="DOC_ASYNC_FATAL", metadata={"error": str(e)}, severity="error")
            try:
                docs_col.update_one(
                    {"doc_id": doc_id, "org_id": org_id},
                    {"$set": {"status": "error", "content": f"Gagal memproses dokumen: {str(e)}"}}
                )
            except Exception:
                pass

    thread = threading.Thread(target=process_document_async)
    thread.daemon = True
    thread.start()

    return jsonify(response_data), 201


@document_bp.route('/list', methods=['GET'])
@token_required
def list_documents(current_user):
    org_id = current_user.get("org_id")
    role = current_user.get("role", "member")
    user_id = current_user.get("user_id")

    delegation_id = current_user.get("delegation_id") or None

    projection = {
        "_id": 0,
        "doc_id": 1,
        "filename": 1,
        "title": 1,
        "content": 1,
        "classification": 1,
        "entities": 1,
        "uploaded_at": 1,
        "uploaded_by": 1,
        "org_id": 1,
        "delegation_id": 1,
        "mimetype": 1,
        "status": 1,
        "google_drive": 1,
    }

    if role == 'owner':
        docs = list(docs_col.find({"org_id": org_id}, projection))
    else:
        is_general = not delegation_id or delegation_id == "general"
        if is_general:
            query = {
                "org_id": org_id,
                "$or": [
                    {"delegation_id": "general"},
                    {"delegation_id": None},
                    {"delegation_id": {"$exists": False}},
                    {"uploaded_by": user_id},
                ]
            }
        else:
            query = {
                "org_id": org_id,
                "$or": [
                    {"delegation_id": delegation_id},
                    {"uploaded_by": user_id},
                ]
            }
        docs = list(docs_col.find(query, projection))

    # Prefetch all delegations for this organization to avoid N+1 queries
    try:
        delegations = list(delegations_col.find({"org_id": org_id}))
        _delegation_cache.clear()
        for d in delegations:
            d_id = d["_id"]
            d_name = d.get("name")
            _delegation_cache[f"{org_id}:{d_id}"] = d_name
            _delegation_cache[f"{org_id}:{str(d_id)}"] = d_name
    except Exception as e:
        log_event("document_service", f"Failed to prefetch delegations: {str(e)}", severity="warning")
        _delegation_cache.clear()

    docs = [_serialize_doc(doc) for doc in docs]

    log_event("document_service", f"Listed docs for org: {org_id}, role: {role}",
              user_id=user_id, org_id=org_id, action="DOC_LIST_VIEW")

    return jsonify(docs), 200


@document_bp.route('/disposition/<path:doc_id>', methods=['POST'])
@token_required
@role_required('owner')
def disposition_document(current_user, doc_id):
    """
    Disposisi surat ke delegasi tertentu (Owner Only)
    """
    org_id = current_user.get("org_id")
    data = request.get_json(force=True, silent=True) or {}
    delegation_id = data.get("delegation_id")

    if not delegation_id:
        return jsonify({"error": "Delegation ID is required"}), 400

    try:
        # Fetch document title first for logging
        doc = docs_col.find_one({"doc_id": doc_id, "org_id": org_id})
        doc_title = doc.get("title", doc.get("filename", "Dokumen")) if doc else "Dokumen"

        # Check if disposition target is general
        if delegation_id == 'general':
            result = docs_col.update_one(
                {"doc_id": doc_id, "org_id": org_id},
                {"$set": {"delegation_id": "general"}}
            )
            if result.matched_count == 0:
                return jsonify({"error": "Document not found"}), 404
            
            log_event(
                "document_service",
                f"Mendisposisikan berkas '{doc_title}' ke Umum (General)",
                user_id=current_user.get("user_id"),
                org_id=org_id,
                action="DOC_DISPOSITION_SUCCESS",
                audience="owner",
                visibility="app",
                severity="info"
            )
            return jsonify({"message": "Document successfully dispositioned to General"}), 200

        # Verify delegation exists in this organization
        delegation = delegations_col.find_one({"_id": ObjectId(delegation_id), "org_id": org_id})
        if not delegation:
            # Try lookup without ObjectId just in case
            delegation = delegations_col.find_one({"_id": delegation_id, "org_id": org_id})
        if not delegation:
            return jsonify({"error": "Delegation not found in this organization"}), 404

        result = docs_col.update_one(
            {"doc_id": doc_id, "org_id": org_id},
            {"$set": {"delegation_id": delegation_id}}
        )

        if result.matched_count == 0:
            return jsonify({"error": "Document not found"}), 404

        log_event(
            "document_service",
            f"Mendisposisikan berkas '{doc_title}' ke divisi {delegation['name']}",
            user_id=current_user.get("user_id"),
            org_id=org_id,
            action="DOC_DISPOSITION_SUCCESS",
            audience="owner",
            visibility="app",
            severity="info"
        )
        return jsonify({"message": f"Document successfully dispositioned to {delegation['name']}"}), 200

    except Exception as e:
        log_event("document_service", f"Failed to disposition document: {str(e)}",
                  user_id=current_user.get("user_id"), org_id=org_id, action="DOC_DISPOSITION_FAILED", severity="error")
        return jsonify({"error": "Failed to disposition document"}), 500


@document_bp.route('/<path:doc_id>', methods=['DELETE'])
@token_required
@role_required('owner')
def delete_document(current_user, doc_id):
    """
    Delete Document by ID (only owner role)
    ---
    tags:
      - Document
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
      - name: doc_id
        in: path
        type: string
        required: true
        description: The unique document ID (hex string) to delete
    responses:
      200:
        description: Document deleted successfully
      401:
        description: Unauthorized
      403:
        description: Forbidden - owner role required
      404:
        description: Document not found
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")
    
    log_event(
        "document_service",
        f"Delete request for doc_id: {doc_id} by {current_user.get('username')}",
        user_id=user_id,
        org_id=org_id,
        action="DOC_DELETE_REQUEST",
        metadata={"doc_id": doc_id}
    )

    doc = docs_col.find_one({"doc_id": doc_id, "org_id": org_id})
    if not doc:
        log_event(
            "document_service",
            f"Document not found or not in org for delete: {doc_id}",
            user_id=user_id,
            org_id=org_id,
            action="DOC_DELETE_FAILED",
            metadata={"doc_id": doc_id}
        )
        return jsonify({"error": "Document not found"}), 404

    drive_delete_success = None

    if doc.get("google_drive") and doc["google_drive"].get("file_id"):
        owner = users_col.find_one({
            "org_id": org_id,
            "role": "owner",
            "google_drive_connected": True
        })

        if owner:
            refresh_token = owner.get("google_oauth", {}).get("refresh_token")
            if refresh_token:
                drive_delete_success = delete_file_from_google_drive(
                    doc["google_drive"]["file_id"],
                    refresh_token
                )
            else:
                drive_delete_success = False
        else:
            drive_delete_success = False

    if drive_delete_success is False:
        log_event(
            "document_service",
            f"Failed to delete document from Google Drive: {doc_id}",
            user_id=user_id,
            org_id=org_id,
            action="DOC_DELETE_FAILED",
            metadata={
                "doc_id": doc_id,
                "drive_delete_success": drive_delete_success
            }
        )
        return jsonify({"error": "Failed to delete document from Google Drive"}), 500

    result = docs_col.delete_one({"doc_id": doc_id, "org_id": org_id})

    if result.deleted_count:
        doc_title = doc.get("title", doc.get("filename", "Dokumen"))
        log_event(
            "document_service",
            f"Menghapus berkas '{doc_title}' secara permanen",
            user_id=user_id,
            org_id=org_id,
            action="DOC_DELETE_SUCCESS",
            metadata={
                "doc_id": doc_id,
                "drive_delete_success": drive_delete_success
            },
            audience="owner" if current_user.get("role") == "owner" else "user",
            visibility="app",
            severity="info",
        )

        return jsonify({
            "message": "Document deleted",
            "google_drive_deleted": drive_delete_success
        }), 200

    return jsonify({"error": "Document not found"}), 404


@document_bp.route('/replace/<path:doc_id>', methods=['PUT', 'POST'])
@token_required
@role_required('owner')
def replace_document(current_user, doc_id):
    """
    Replace and Re-process Document
    ---
    tags:
      - Document
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    description: >
      Replace an existing document by providing either a new image file
      (which will be re-processed through OCR) or raw text.
      The document will be re-classified and re-analyzed for entities.
      If a file is provided, it takes priority over the text field.
      Only documents belonging to the user's organization can be updated.
    consumes:
      - multipart/form-data
    parameters:
      - name: doc_id
        in: path
        type: string
        required: true
        description: The unique document ID (hex string) to replace
      - name: file
        in: formData
        type: file
        required: false
        description: (Optional) New image file to re-process through OCR
      - name: text
        in: formData
        type: string
        required: false
        description: (Optional) New raw text content to replace the document with
    responses:
      200:
        description: Document updated and re-processed successfully
      400:
        description: No file or text provided
      401:
        description: Unauthorized
      404:
        description: Document not found
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")
    
    log_event("document_service", f"Replace request for doc_id: {doc_id} by {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="DOC_REPLACE_REQUEST", metadata={"doc_id": doc_id})

    existing = docs_col.find_one({"doc_id": doc_id, "org_id": org_id})
    if not existing:
        return jsonify({"error": "Document not found"}), 404

    new_text = ""
    new_filename = existing.get("filename", "")

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        new_filename = file.filename
        try:
            files = {'file': (file.filename, file.stream, file.mimetype)}
            ocr_res = requests.post(f"{GATEWAY_URL}/ocr/extract-text", files=files, headers=_get_auth_header())
            ocr_res.raise_for_status()
            new_text = ocr_res.json().get("text", "")
        except Exception as e:
            log_event("document_service", f"OCR request failed during replace: {str(e)}",
                      user_id=user_id, org_id=org_id, action="DOC_REPLACE_OCR_FAILED", severity="error")
            return jsonify({"error": "OCR failed"}), 500
    elif request.form.get("text"):
        new_text = request.form.get("text")
    elif request.get_json(force=True, silent=True) and request.get_json(force=True, silent=True).get("text"):
        new_text = request.get_json(force=True, silent=True).get("text")

    if not new_text:
        return jsonify({"error": "Either a file or text must be provided"}), 400

    classification, entities = process_ai_pipeline(new_text)
    new_title = generate_document_title(new_text, new_filename)

    update_data = {
        "filename": new_filename,
        "title": new_title,
        "content": new_text,
        "classification": classification,
        "entities": entities,
        "updated_at": datetime.datetime.utcnow(),
        "updated_by": user_id,
        "status": "re-processed"
    }

    docs_col.update_one({"doc_id": doc_id, "org_id": org_id}, {"$set": update_data})
    
    log_event("document_service", f"Document replaced and re-processed: {doc_id}",
              user_id=user_id, org_id=org_id, action="DOC_REPLACE_SUCCESS", metadata={"doc_id": doc_id},
              audience="owner" if current_user.get("role") == "owner" else "user",
              visibility="app",
              severity="info")

    return jsonify({
        "message": "Document updated and re-processed",
        "doc_id": doc_id,
        "filename": new_filename,
        "title": new_title,
        "classification": classification,
        "entities": entities
    }), 200

@document_bp.route('/<path:doc_id>', methods=['GET'])
@token_required
def get_document_detail(current_user, doc_id):
    """
    Get Document Detail by ID
    ---
    tags:
      - Document
    security:
      - BearerAuth: []
    parameters:
      - name: doc_id
        in: path
        type: string
        required: true
        description: The unique document ID (hex string)
    responses:
      200:
        description: Returns the full document details along with dynamic security suggestions if not uploaded to Google Drive
      404:
        description: Document not found
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")
    
    doc = docs_col.find_one({"doc_id": doc_id, "org_id": org_id})
    if not doc:
        return jsonify({"error": "Document not found"}), 404
        
    doc = _serialize_doc(doc)
    
    # Jika Google Drive belum terhubung, generate saran keamanan dinamis dengan Mistral AI
    if not doc.get("google_drive"):
        doc["security_suggestion"] = generate_security_suggestion(doc)
    else:
        doc["security_suggestion"] = None
        
    return jsonify(doc), 200


@document_bp.route('/download/<path:doc_id>', methods=['GET'])
@token_required
def download_document(current_user, doc_id):
    """
    Download Document File
    ---
    tags:
      - Document
    produces:
      - application/octet-stream
    security:
      - BearerAuth: []
    parameters:
      - name: doc_id
        in: path
        type: string
        required: true
        description: Unique document ID to download
    responses:
      200:
        description: Document file downloaded successfully
      400:
        description: Google Drive is not connected or refresh token is missing
      401:
        description: Unauthorized - invalid or missing token
      404:
        description: Document not found or file source unavailable
      500:
        description: Download failed
    """
    org_id = current_user.get("org_id")

    doc = docs_col.find_one({"doc_id": doc_id, "org_id": org_id})
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    filename = doc.get("filename", "document")
    mimetype = doc.get("mimetype", "application/octet-stream")

    try:
        if doc.get("google_drive") and doc["google_drive"].get("file_id"):
            owner = users_col.find_one({
                "org_id": org_id,
                "role": "owner",
                "google_drive_connected": True
            })

            if not owner:
                return jsonify({"error": "Organization owner's Google Drive is not connected"}), 400

            refresh_token = owner.get("google_oauth", {}).get("refresh_token")
            if not refresh_token:
                return jsonify({"error": "Missing owner's Google refresh token"}), 400

            file_id = doc["google_drive"]["file_id"]
            file_bytes = download_file_from_google_drive(file_id, refresh_token)

        elif doc.get("file_data"):
            file_bytes = base64.b64decode(doc["file_data"])

        else:
            return jsonify({"error": "Document file source is not available"}), 404

        return send_file(
            BytesIO(file_bytes),
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        log_event(
            "document_service",
            f"Download document failed: {str(e)}",
            org_id=org_id,
            action="DOC_DOWNLOAD_FAILED",
            severity="error"
        )
        return jsonify({"error": "Download failed"}), 500

@document_bp.route('/migrate-to-drive', methods=['POST'])
def migrate_to_drive():
    """
    Migrasi dokumen fisik lama dari MongoDB (Base64) ke Google Drive setelah user terhubung
    """

    

    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id")
    
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400
        
    # Ambil data token Google Drive milik user
    user = users_col.find_one({"_id": ObjectId(user_id)})
    if not user or not user.get("google_drive_connected"):
        return jsonify({"error": "User's Google Drive is not connected"}), 400
        
    refresh_token = user.get("google_oauth", {}).get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "Missing Google refresh token"}), 400
        
    # Ambil semua dokumen milik user ini yang masih disimpan di MongoDB (memiliki file_data dan tidak memiliki google_drive)
    org_id = user.get("org_id")

    docs_to_migrate = list(docs_col.find({
        "org_id": org_id,
        "file_data": {"$exists": True, "$ne": None},
        "google_drive": None
    }))
    
    total_to_migrate = len(docs_to_migrate)
    migrated_count = 0
    failed_count = 0
    
    for doc in docs_to_migrate:
        try:
            file_data_b64 = doc.get("file_data")
            mimetype = doc.get("mimetype", "image/jpeg")
            filename = doc.get("filename", "document.jpg")
            
            # Decode base64 ke file stream
            file_bytes = base64.b64decode(file_data_b64)
            file_stream = BytesIO(file_bytes)
            
            # Upload ke Google Drive
            drive_data = upload_file_to_google_drive(
                file_stream=file_stream,
                filename=filename,
                mimetype=mimetype,
                refresh_token=refresh_token
            )
            
            # Update record dokumen di MongoDB:
            # 1. Set google_drive field dengan data tautan Drive
            # 2. Hapus (purge) file_data biner dari MongoDB untuk menghemat storage
            docs_col.update_one(
                {"doc_id": doc["doc_id"]},
                {
                    "$set": {"google_drive": drive_data},
                    "$unset": {"file_data": ""}
                }
            )
            migrated_count += 1
            
        except Exception as e:
            failed_count += 1
            log_event("document_service", f"Gagal migrasi dokumen {doc.get('doc_id')}: {str(e)}", action="MIGRATION_DOC_FAILED")
            
    log_event("document_service", f"Sukses migrasi {migrated_count} dokumen ke Google Drive untuk user {user_id}", action="MIGRATION_SUCCESS")
    
    return jsonify({
        "message": f"Successfully migrated {migrated_count} documents to Google Drive",
        "migrated_count": migrated_count,
        "failed_count": failed_count,
        "total_to_migrate": total_to_migrate
    }), 200


@document_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "document_service"}), 200

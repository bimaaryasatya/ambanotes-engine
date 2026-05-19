import os
import sys

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
from common.logger import log_event
from common.jwt_utils import token_required, role_required

import requests
from common.db import docs_col, users_col
from bson.objectid import ObjectId
import uuid
import datetime
import base64
from io import BytesIO
from common.google_drive_client import upload_file_to_google_drive

from common.config import Config

document_bp = Blueprint('document', __name__)

# Use central configuration
GATEWAY_URL = Config.GATEWAY_URL

def _get_auth_header():
    """Ambil Authorization header dari request yang sedang aktif untuk diteruskan ke service internal."""
    return {"Authorization": request.headers.get("Authorization", "")}


def process_ai_pipeline(text):
    """Fungsi helper untuk menjalankan Klasifikasi dan NER (meneruskan token auth)."""
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

    try:
        files = {'file': (file.filename, file.stream, file.mimetype)}
        ocr_res = requests.post(f"{GATEWAY_URL}/ocr/extract-text", files=files, headers=_get_auth_header())
        ocr_res.raise_for_status()
        extracted_text = ocr_res.json().get("text", "")
    except Exception as e:
        log_event("document_service", f"OCR request failed: {str(e)}", 
                  user_id=user_id, org_id=org_id, action="DOC_OCR_FAILED", metadata={"error": str(e)})
        return jsonify({"error": f"OCR failed: {str(e)}"}), 500

    classification, entities = process_ai_pipeline(extracted_text)

    # Reset stream pointer setelah dibaca oleh request POST OCR agar bisa dibaca ulang
    file.stream.seek(0)

    # 1. Periksa koneksi Google Drive
    user_data = users_col.find_one({"_id": ObjectId(user_id)})
    google_drive_data = None
    file_data_b64 = None

    google_drive_connected = user_data.get("google_drive_connected", False) if user_data else False

    if google_drive_connected:
        refresh_token = user_data.get("google_oauth", {}).get("refresh_token")
        if refresh_token:
            try:
                # Upload file fisik asli ke Google Drive user
                google_drive_data = upload_file_to_google_drive(
                    file_stream=file.stream,
                    filename=file.filename,
                    mimetype=file.mimetype,
                    refresh_token=refresh_token
                )
                log_event("document_service", f"Successfully uploaded file {file.filename} to user's Google Drive", 
                          user_id=user_id, org_id=org_id, action="DOC_DRIVE_UPLOAD_SUCCESS")
            except Exception as drive_err:
                log_event("document_service", f"Failed to upload to Google Drive: {str(drive_err)}, falling back to local Base64", 
                          user_id=user_id, org_id=org_id, action="DOC_DRIVE_UPLOAD_FAILED")
                # Fallback ke penyimpanan lokal/Base64 di MongoDB jika Drive upload gagal
                file.stream.seek(0)
                file_data_b64 = base64.b64encode(file.stream.read()).decode("utf-8")
        else:
            # Fallback ke penyimpanan lokal/Base64 jika refresh token tidak tersedia
            file_data_b64 = base64.b64encode(file.stream.read()).decode("utf-8")
    else:
        # Google Drive belum terhubung: simpan file asli sebagai Base64 di MongoDB
        file_data_b64 = base64.b64encode(file.stream.read()).decode("utf-8")

    doc_id = uuid.uuid4().hex
    doc_data = {
        "doc_id": doc_id,
        "filename": file.filename,
        "content": extracted_text,
        "classification": classification,
        "entities": entities,
        "uploaded_at": datetime.datetime.utcnow(),
        "uploaded_by": user_id,
        "org_id": org_id,
        "google_drive": google_drive_data,
        "mimetype": file.mimetype,
        "status": "processed"
    }

    if file_data_b64:
        doc_data["file_data"] = file_data_b64

    docs_col.insert_one(doc_data)
    doc_data.pop('_id', None)

    # 2. Hasilkan saran keamanan dinamis dengan Mistral AI jika belum terhubung
    if not google_drive_data:
        doc_data["security_suggestion"] = generate_security_suggestion(doc_data)
    else:
        doc_data["security_suggestion"] = None

    log_event("document_service", f"File processed and saved: {file.filename}", 
              user_id=user_id, org_id=org_id, action="DOC_UPLOAD_SUCCESS", 
              metadata={"doc_id": doc_id, "filename": file.filename})
              
    return jsonify(doc_data), 201


@document_bp.route('/list', methods=['GET'])
@token_required
def list_documents(current_user):
    """
    List all processed documents (filtered by organization)
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
    responses:
      200:
        description: List of documents belonging to the user's organization
      401:
        description: Unauthorized
    """
    org_id = current_user.get("org_id")
    docs = list(docs_col.find({"org_id": org_id}))
    for doc in docs:
        doc.pop('_id', None)
        
    log_event("document_service", f"Listed docs for org: {org_id}", 
              user_id=current_user.get("user_id"), org_id=org_id, action="DOC_LIST_VIEW")
              
    return jsonify(docs), 200


@document_bp.route('/<doc_id>', methods=['DELETE'])
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
    
    log_event("document_service", f"Delete request for doc_id: {doc_id} by {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="DOC_DELETE_REQUEST", metadata={"doc_id": doc_id})

    result = docs_col.delete_one({"doc_id": doc_id, "org_id": org_id})
    if result.deleted_count:
        log_event("document_service", f"Document deleted: {doc_id}", 
                  user_id=user_id, org_id=org_id, action="DOC_DELETE_SUCCESS", metadata={"doc_id": doc_id})
        return jsonify({"message": "Document deleted"}), 200
        
    log_event("document_service", f"Document not found or not in org for delete: {doc_id}",
              user_id=user_id, org_id=org_id, action="DOC_DELETE_FAILED", metadata={"doc_id": doc_id})
    return jsonify({"error": "Document not found"}), 404


@document_bp.route('/replace/<doc_id>', methods=['PUT'])
@token_required
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
                      user_id=user_id, org_id=org_id, action="DOC_REPLACE_OCR_FAILED")
            return jsonify({"error": f"OCR failed: {str(e)}"}), 500
    elif request.form.get("text"):
        new_text = request.form.get("text")
    elif request.get_json(force=True, silent=True) and request.get_json(force=True, silent=True).get("text"):
        new_text = request.get_json(force=True, silent=True).get("text")

    if not new_text:
        return jsonify({"error": "Either a file or text must be provided"}), 400

    classification, entities = process_ai_pipeline(new_text)

    update_data = {
        "filename": new_filename,
        "content": new_text,
        "classification": classification,
        "entities": entities,
        "updated_at": datetime.datetime.utcnow(),
        "updated_by": user_id,
        "status": "re-processed"
    }

    docs_col.update_one({"doc_id": doc_id, "org_id": org_id}, {"$set": update_data})
    
    log_event("document_service", f"Document replaced and re-processed: {doc_id}",
              user_id=user_id, org_id=org_id, action="DOC_REPLACE_SUCCESS", metadata={"doc_id": doc_id})

    return jsonify({
        "message": "Document updated and re-processed",
        "doc_id": doc_id,
        "filename": new_filename,
        "classification": classification,
        "entities": entities
    }), 200


@document_bp.route('/<doc_id>', methods=['GET'])
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
        
    doc.pop('_id', None)
    
    # Jika Google Drive belum terhubung, generate saran keamanan dinamis dengan Mistral AI
    if not doc.get("google_drive"):
        doc["security_suggestion"] = generate_security_suggestion(doc)
    else:
        doc["security_suggestion"] = None
        
    return jsonify(doc), 200


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
    docs_to_migrate = list(docs_col.find({
        "uploaded_by": user_id,
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

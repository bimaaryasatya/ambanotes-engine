import os
import sys

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
from common.logger import log_event
from common.jwt_utils import token_required, role_required

import requests
from common.db import docs_col
import uuid
import datetime

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
        "status": "processed"
    }

    docs_col.insert_one(doc_data)
    doc_data.pop('_id', None)

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


@document_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "document_service"}), 200

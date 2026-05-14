import os
import sys

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
import requests
from common.db import docs_col
from common.logger import log_event
import uuid
import datetime

document_bp = Blueprint('document', __name__)

# Base URL Gateway (karena kita jalan di satu port yang sama)
GATEWAY_URL = "http://localhost:5009"

def process_ai_pipeline(text):
    """Fungsi helper untuk menjalankan Klasifikasi dan NER"""
    try:
        # 1. Klasifikasi
        class_res = requests.post(f"{GATEWAY_URL}/classification/predict", json={"text": text})
        classification = class_res.json() if class_res.status_code == 200 else {"label": "Unknown"}

        # 2. NER
        ner_res = requests.post(f"{GATEWAY_URL}/ner/extract", json={"text": text})
        entities = ner_res.json() if ner_res.status_code == 200 else {}

        return classification, entities
    except Exception as e:
        log_event("document_service", f"AI Pipeline error: {str(e)}")
        return {"label": "Error"}, {}

@document_bp.route('/upload', methods=['POST'])
def upload_document():
    """
    Upload and Process Image File (OCR -> Classify -> NER)
    ---
    tags:
      - Document
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
    """
    log_event("document_service", "Starting file upload and processing")
    
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']

    # 1. Kirim file ke OCR Service
    try:
        # Gunakan 'files' parameter di requests untuk mengirim stream file
        files = {'file': (file.filename, file.stream, file.mimetype)}
        ocr_res = requests.post(f"{GATEWAY_URL}/ocr/extract-text", files=files)
        ocr_res.raise_for_status()
        extracted_text = ocr_res.json().get("text", "")
    except Exception as e:
        log_event("document_service", f"OCR request failed: {str(e)}")
        return jsonify({"error": f"OCR failed: {str(e)}"}), 500

    # 2. Jalankan Pipeline AI (Klasifikasi & NER)
    classification, entities = process_ai_pipeline(extracted_text)

    # 3. Simpan ke MongoDB
    doc_data = {
        "doc_id": uuid.uuid4().hex,
        "filename": file.filename,
        "content": extracted_text,
        "classification": classification,
        "entities": entities,
        "uploaded_at": datetime.datetime.utcnow(),
        "status": "processed"
    }
    
    docs_col.insert_one(doc_data)
    doc_data.pop('_id', None)
    
    log_event("document_service", f"File processed and saved: {file.filename}")
    return jsonify(doc_data), 201

@document_bp.route('/<doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """
    Delete Document by ID
    ---
    tags:
      - Document
    parameters:
      - name: doc_id
        in: path
        type: string
        required: true
        description: The unique document ID (hex string) to delete
    responses:
      200:
        description: Document deleted successfully
        schema:
          type: object
          properties:
            message:
              type: string
              example: Document deleted
      404:
        description: Document not found
        schema:
          type: object
          properties:
            error:
              type: string
              example: Document not found
    """
    log_event("document_service", f"Delete request for doc_id: {doc_id}")
    result = docs_col.delete_one({"doc_id": doc_id})
    if result.deleted_count:
        log_event("document_service", f"Document deleted: {doc_id}")
        return jsonify({"message": "Document deleted"}), 200
    log_event("document_service", f"Document not found for delete: {doc_id}")
    return jsonify({"error": "Document not found"}), 404

@document_bp.route('/replace/<doc_id>', methods=['PUT'])
def replace_document(doc_id):
    """
    Replace and Re-process Document
    ---
    tags:
      - Document
    description: >
      Replace an existing document by providing either a new image file
      (which will be re-processed through OCR) or raw text.
      The document will be re-classified and re-analyzed for entities.
      If a file is provided, it takes priority over the text field.
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
        schema:
          type: object
          properties:
            message:
              type: string
              example: Document updated and re-processed
            doc_id:
              type: string
            classification:
              type: object
            entities:
              type: object
      400:
        description: No file or text provided
        schema:
          type: object
          properties:
            error:
              type: string
              example: Either a file or text must be provided
      404:
        description: Document not found
        schema:
          type: object
          properties:
            error:
              type: string
              example: Document not found
    """
    log_event("document_service", f"Replace request for doc_id: {doc_id}")

    # Check if document exists first
    existing = docs_col.find_one({"doc_id": doc_id})
    if not existing:
        log_event("document_service", f"Document not found for replace: {doc_id}")
        return jsonify({"error": "Document not found"}), 404

    new_text = ""
    new_filename = existing.get("filename", "")

    # Priority 1: File upload -> re-OCR
    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        new_filename = file.filename
        try:
            files = {'file': (file.filename, file.stream, file.mimetype)}
            ocr_res = requests.post(f"{GATEWAY_URL}/ocr/extract-text", files=files)
            ocr_res.raise_for_status()
            new_text = ocr_res.json().get("text", "")
        except Exception as e:
            log_event("document_service", f"OCR request failed during replace: {str(e)}")
            return jsonify({"error": f"OCR failed: {str(e)}"}), 500
    # Priority 2: Text from form or JSON body
    elif request.form.get("text"):
        new_text = request.form.get("text")
    elif request.json and request.json.get("text"):
        new_text = request.json.get("text")

    if not new_text:
        return jsonify({"error": "Either a file or text must be provided"}), 400

    # Re-run AI Pipeline
    classification, entities = process_ai_pipeline(new_text)

    # Update Database
    update_data = {
        "filename": new_filename,
        "content": new_text,
        "classification": classification,
        "entities": entities,
        "updated_at": datetime.datetime.utcnow(),
        "status": "re-processed"
    }

    docs_col.update_one({"doc_id": doc_id}, {"$set": update_data})
    log_event("document_service", f"Document replaced and re-processed: {doc_id}")

    return jsonify({
        "message": "Document updated and re-processed",
        "doc_id": doc_id,
        "filename": new_filename,
        "classification": classification,
        "entities": entities
    }), 200

@document_bp.route('/list', methods=['GET'])
def list_documents():
    """
    List all processed documents
    ---
    tags:
      - Document
    """
    docs = list(docs_col.find())
    for doc in docs:
        doc.pop('_id', None) # Hapus ID MongoDB agar bisa di-JSON-kan
    return jsonify(docs), 200

@document_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "document_service"}), 200

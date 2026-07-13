import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
from common.logger import log_event
from common.jwt_utils import token_required
from common.config import Config
import google.generativeai as genai

# Konfigurasi Gemini API
genai.configure(api_key=Config.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-flash-latest')

ocr_bp = Blueprint('ocr', __name__)


@ocr_bp.route('/extract-text', methods=['POST'])
@token_required
def extract_text(current_user):
    """
    Extract text from image file
    ---
    tags:
      - OCR
    security:
      - BearerAuth: []
    consumes:
      - multipart/form-data
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
      - name: file
        in: formData
        type: file
        required: true
        description: The image file to process
    responses:
      200:
        description: Text extracted from image
        schema:
          type: object
          properties:
            text:
              type: string
      400:
        description: No file provided
      401:
        description: Unauthorized
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    if 'file' not in request.files:
        log_event("ocr_service", "No file found in request", user_id=user_id, org_id=org_id, action="OCR_MISSING_FILE")
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    log_event("ocr_service", f"Processing file: {file.filename} for user: {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="OCR_START", metadata={"filename": file.filename})

    try:
        image_data = file.read()
        
        # Try Mistral Document AI (OCR) first
        try:
            import requests
            
            # Step 1: Upload file to Mistral Files API with purpose="ocr"
            upload_url = "https://api.mistral.ai/v1/files"
            upload_headers = {
                "Authorization": f"Bearer {Config.MISTRAL_API_KEY}"
            }
            files_payload = {
                "file": (file.filename, image_data, file.content_type)
            }
            data_payload = {
                "purpose": "ocr"
            }
            
            upload_res = requests.post(
                upload_url,
                headers=upload_headers,
                files=files_payload,
                data=data_payload,
                timeout=30
            )
            upload_res.raise_for_status()
            file_id = upload_res.json()["id"]
            
            # Step 2: Run OCR & Delete file in try-finally block
            try:
                ocr_url = "https://api.mistral.ai/v1/ocr"
                ocr_headers = {
                    "Authorization": f"Bearer {Config.MISTRAL_API_KEY}",
                    "Content-Type": "application/json"
                }
                ocr_payload = {
                    "model": "mistral-ocr-latest",
                    "document": {
                        "file_id": file_id
                    }
                }
                
                ocr_res = requests.post(
                    ocr_url,
                    headers=ocr_headers,
                    json=ocr_payload,
                    timeout=30
                )
                ocr_res.raise_for_status()
                ocr_data = ocr_res.json()
                
                # Extract markdown content from all pages
                pages = ocr_data.get("pages", [])
                text = "\n".join([page.get("markdown", "") for page in pages])
                
            finally:
                # Cleanup the uploaded file from Mistral
                try:
                    requests.delete(
                        f"https://api.mistral.ai/v1/files/{file_id}",
                        headers={"Authorization": f"Bearer {Config.MISTRAL_API_KEY}"},
                        timeout=10
                    )
                except Exception:
                    pass  # Fail silently on cleanup failure
            
            log_event("ocr_service", f"OCR Successful (Mistral Document AI) for {file.filename}",
                      user_id=user_id, org_id=org_id, action="OCR_SUCCESS", metadata={"filename": file.filename, "provider": "mistral_ocr"})
            return jsonify({"text": text.strip()}), 200
            
        except Exception as mistral_err:
            log_event("ocr_service", f"OCR failed with Mistral Document AI ({str(mistral_err)}), falling back to Gemini",
                      user_id=user_id, org_id=org_id, action="OCR_FALLBACK_GEMINI", metadata={"error": str(mistral_err)}, severity="warning")
            
            response = model.generate_content([
                "Ekstrak semua teks dari gambar ini seakurat mungkin. Berikan hanya teks hasil ekstraksi tanpa tambahan komentar apa pun.",
                {"mime_type": file.content_type, "data": image_data}
            ])
            text = response.text
            log_event("ocr_service", f"OCR Successful (Gemini fallback) for {file.filename}",
                      user_id=user_id, org_id=org_id, action="OCR_SUCCESS", metadata={"filename": file.filename, "provider": "gemini"})
            return jsonify({"text": text.strip()}), 200
            
    except Exception as e:
        log_event("ocr_service", f"OCR Failed (All Providers): {str(e)}",
                  user_id=user_id, org_id=org_id, action="OCR_FAILED", metadata={"error": str(e)}, severity="error")
        return jsonify({"error": "OCR processing failed"}), 500

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
    if 'file' not in request.files:
        log_event("ocr_service", "No file found in request")
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    log_event("ocr_service", f"Processing file: {file.filename} for user: {current_user.get('username')}")

    try:
        image_data = file.read()
        response = model.generate_content([
            "Ekstrak semua teks dari gambar ini seakurat mungkin. Berikan hanya teks hasil ekstraksi tanpa tambahan komentar apa pun.",
            {"mime_type": file.content_type, "data": image_data}
        ])
        text = response.text
        log_event("ocr_service", f"OCR Successful (Gemini) for {file.filename}")
        return jsonify({"text": text.strip()}), 200
    except Exception as e:
        log_event("ocr_service", f"OCR Failed (Gemini): {str(e)}")
        return jsonify({"error": f"OCR processing failed: {str(e)}"}), 500

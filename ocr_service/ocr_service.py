import os
import sys

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
from common.logger import log_event

ocr_bp = Blueprint('ocr', __name__)

@ocr_bp.route('/extract-text', methods=['POST'])
def extract_text():
    """
    Extract text from image (Placeholder)
    ---
    tags:
      - OCR
    responses:
      200:
        description: Text extracted
    """
    log_event("ocr_service", "OCR extraction request received")
    # Placeholder: Nanti gunakan library OCR seperti Tesseract atau EasyOCR
    text = "Ini adalah hasil dummy OCR dari gambar yang diupload."
    
    return jsonify({"text": text}), 200

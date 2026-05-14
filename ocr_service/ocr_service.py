from flask import Blueprint, jsonify, request
from common.logger import log_event
import pytesseract
from PIL import Image
import io

# Jika Tesseract tidak ada di PATH, Anda perlu mengarahkan ke path eksekusinya
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

ocr_bp = Blueprint('ocr', __name__)

@ocr_bp.route('/extract-text', methods=['POST'])
def extract_text():
    """
    Extract text from image file
    ---
    tags:
      - OCR
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
    """
    if 'file' not in request.files:
        log_event("ocr_service", "No file found in request")
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    log_event("ocr_service", f"Processing file: {file.filename}")
    
    try:
        # Buka gambar menggunakan PIL
        img = Image.open(file.stream)
        
        # Jalankan Tesseract OCR
        # --psm 6 berasumsi teks berupa blok seragam
        text = pytesseract.image_to_string(img, lang='ind+eng')
        
        log_event("ocr_service", f"OCR Successful for {file.filename}")
        return jsonify({"text": text.strip()}), 200
    except Exception as e:
        log_event("ocr_service", f"OCR Failed: {str(e)}")
        return jsonify({"error": f"OCR processing failed: {str(e)}"}), 500

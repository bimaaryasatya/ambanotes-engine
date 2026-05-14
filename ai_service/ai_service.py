import os
import sys

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify
import requests
from common.config import Config
from common.logger import log_event

ai_bp = Blueprint('ai', __name__)

@ai_bp.route("/process", methods=["POST"])
def process():
    """
    Process document text with Mistral AI
    ---
    tags:
      - AI
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            text:
              type: string
              example: "Tolong rangkum dokumen ini..."
    responses:
      200:
        description: AI processing results
      500:
        description: Error processing request
    """
    log_event("ai_service", "Processing text with AI")
    try:
        text = request.json.get("text", "")
        if not text:
            return jsonify({"error": "No text provided"}), 400

        prompt = f"""
        Analisa dokumen berikut:
        1. Klasifikasi
        2. Ringkasan
        3. Entity (nama, tanggal, nominal)

        Text:
        {text}
        """

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

        log_event("ai_service", "AI processing completed successfully")
        return jsonify({
            "classification": result,
            "summary": result,
            "entities": result
        }), 200

    except Exception as e:
        log_event("ai_service", f"AI processing error: {str(e)}")
        return jsonify({"error": str(e)}), 500

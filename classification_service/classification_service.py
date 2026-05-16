import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify
from common.logger import log_event
from common.jwt_utils import token_required
from common.config import Config
from transformers import pipeline, AutoModelForSequenceClassification, AutoTokenizer
import google.generativeai as genai

classification_bp = Blueprint('classification', __name__)

# Configure Gemini
genai.configure(api_key=Config.GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-pro')

LABEL_MAPPING = {
    "LABEL_0": "Surat Undangan",
    "LABEL_1": "Surat Permohonan",
    "LABEL_2": "Surat Tugas",
    "LABEL_3": "Surat Keputusan",
    "LABEL_4": "Surat Edaran"
}

# Reverse mapping for Gemini result processing
REVERSE_LABEL_MAPPING = {v: k for k, v in LABEL_MAPPING.items()}

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "surat_model")

try:
    log_event("classification_service", f"Loading model from {MODEL_PATH}", action="MODEL_LOAD_START")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH, use_safetensors=True)
    classifier = pipeline("text-classification", model=model, tokenizer=tokenizer)
    log_event("classification_service", "Model loaded successfully", action="MODEL_LOAD_SUCCESS")
except Exception as e:
    log_event("classification_service", f"Failed to load model: {str(e)}", action="MODEL_LOAD_FAILED", metadata={"error": str(e)})
    classifier = None


def _predict_gemini(text):
    """Classification helper using Gemini API."""
    prompt = f"""
    Klasifikasikan teks surat berikut ke dalam salah satu kategori berikut:
    - Surat Undangan
    - Surat Permohonan
    - Surat Tugas
    - Surat Keputusan
    - Surat Edaran

    Berikan jawaban HANYA berupa nama kategori tersebut tanpa penjelasan atau komentar tambahan.

    Teks Surat:
    {text}
    """
    response = gemini_model.generate_content(prompt)
    category = response.text.strip()
    
    # Validation and mapping
    if category not in LABEL_MAPPING.values():
        # Fallback if Gemini gives something else
        return {
            "label": "LABEL_0",
            "label_name": "Surat Undangan",
            "score": 0.5,
            "provider": "gemini"
        }
    
    return {
        "label": REVERSE_LABEL_MAPPING.get(category),
        "label_name": category,
        "score": 1.0,
        "provider": "gemini"
    }


@classification_bp.route('/predict', methods=['POST'])
@token_required
def predict(current_user):
    """
    Classify a document text (Hybrid: Local or Gemini).
    ---
    tags:
      - Classification
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
          properties:
            text:
              type: string
              example: "kami mengundang anda untuk hadir"
            model_type:
              type: string
              enum: [local, gemini]
              default: local
              description: Pilih model klasifikasi (local atau online gemini)
    responses:
      200:
        description: Successful prediction
      400:
        description: Bad request
      401:
        description: Unauthorized
      500:
        description: Model not loaded or internal error
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    data = request.get_json(force=True, silent=True) or {}
    text = data.get('text', '')
    model_type = data.get('model_type', 'local').lower()

    log_event("classification_service", f"Predict request ({model_type}) from: {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="CLASS_PREDICT_START", metadata={"model_type": model_type})

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        if model_type == 'gemini':
            result = _predict_gemini(text)
        else:
            # Default to local
            if classifier is None:
                return jsonify({"error": "Local model is not loaded. Please use model_type='gemini' as fallback."}), 500
            
            raw_result = classifier(text)[0]
            original_label = raw_result.get('label')
            result = {
                "label": original_label,
                "label_name": LABEL_MAPPING.get(original_label, "Unknown"),
                "score": float(raw_result.get('score', 0)),
                "provider": "local"
            }
        
        log_event("classification_service", f"Prediction successful ({model_type}): {result['label_name']}",
                  user_id=user_id, org_id=org_id, action="CLASS_PREDICT_SUCCESS", metadata={"result": result})
        return jsonify(result), 200

    except Exception as e:
        log_event("classification_service", f"Prediction error ({model_type}): {str(e)}",
                  user_id=user_id, org_id=org_id, action="CLASS_PREDICT_FAILED", metadata={"error": str(e)})
        return jsonify({"error": str(e)}), 500


@classification_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy", 
        "service": "classification_service",
        "local_model_loaded": classifier is not None
    }), 200

import os
import sys

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify
from transformers import pipeline, AutoModelForSequenceClassification, AutoTokenizer
from common.logger import log_event

classification_bp = Blueprint('classification', __name__)

# Load Model
MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "surat_model")

try:
    log_event("classification_service", f"Loading model from {MODEL_PATH}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH, use_safetensors=True)
    classifier = pipeline("text-classification", model=model, tokenizer=tokenizer)
    log_event("classification_service", "Model loaded successfully")
except Exception as e:
    log_event("classification_service", f"Failed to load model: {str(e)}")
    classifier = None

@classification_bp.route('/predict', methods=['POST'])
def predict():
    """
    Classify a document text.
    ---
    tags:
      - Classification
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            text:
              type: string
              example: "kami mengundang anda untuk hadir"
    responses:
      200:
        description: Successful prediction
        schema:
          type: object
          properties:
            label:
              type: string
            score:
              type: number
      400:
        description: Bad request
      500:
        description: Model not loaded or internal error
    """
    log_event("classification_service", "Received predict request")
    if classifier is None:
        log_event("classification_service", "Prediction failed: Model is not loaded")
        return jsonify({"error": "Model is not loaded"}), 500

    data = request.json
    if not data or 'text' not in data:
        return jsonify({"error": "No text provided"}), 400

    text = data['text']
    try:
        result = classifier(text)[0]
        log_event("classification_service", f"Prediction successful: {result}")
        return jsonify(result), 200
    except Exception as e:
        log_event("classification_service", f"Prediction error: {str(e)}")
        return jsonify({"error": str(e)}), 500

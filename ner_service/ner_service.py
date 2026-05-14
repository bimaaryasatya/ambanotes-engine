import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify
from common.logger import log_event
from common.jwt_utils import token_required
from transformers import pipeline

# Load NER Pipeline menggunakan IndoBERT
try:
    log_event("ner_service", "Loading IndoBERT NER model...", action="MODEL_LOAD_START")
    ner_pipeline = pipeline(
        "ner",
        model="cahya/bert-base-indonesian-NER",
        aggregation_strategy="simple"
    )
    log_event("ner_service", "IndoBERT NER model loaded successfully", action="MODEL_LOAD_SUCCESS")
except Exception as e:
    log_event("ner_service", f"Failed to load NER model: {str(e)}", action="MODEL_LOAD_FAILED", metadata={"error": str(e)})
    ner_pipeline = None

ner_bp = Blueprint('ner', __name__)


@ner_bp.route('/extract', methods=['POST'])
@token_required
def extract_entities(current_user):
    """
    Extract entities from text using IndoBERT
    ---
    tags:
      - NER
    security:
      - BearerAuth: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            text:
              type: string
              example: "Bima Sunu adalah mahasiswa dari Tegal."
    responses:
      200:
        description: List of extracted entities
      400:
        description: No text provided
      401:
        description: Unauthorized
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    data = request.json or {}
    text = data.get('text', '')

    if not text:
        return jsonify({"error": "No text provided"}), 400

    if not ner_pipeline:
        return jsonify({"names": [], "locations": [], "dates": [], "others": []}), 200

    try:
        entities = ner_pipeline(text)

        result = {"names": [], "locations": [], "dates": [], "others": []}

        for ent in entities:
            label = ent['entity_group']
            word = ent['word']
            if label == 'PER':
                if word not in result['names']:
                    result['names'].append(word)
            elif label == 'LOC':
                if word not in result['locations']:
                    result['locations'].append(word)
            elif label == 'ORG':
                if f"ORG: {word}" not in result['others']:
                    result['others'].append(f"ORG: {word}")

        log_event("ner_service", f"Extraction successful: {len(entities)} entities found",
                  user_id=user_id, org_id=org_id, action="NER_SUCCESS", metadata={"entity_count": len(entities)})
        return jsonify(result), 200
    except Exception as e:
        log_event("ner_service", f"Extraction failed: {str(e)}",
                  user_id=user_id, org_id=org_id, action="NER_FAILED", metadata={"error": str(e)})
        return jsonify({"error": str(e)}), 500


@ner_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "ner_service"}), 200

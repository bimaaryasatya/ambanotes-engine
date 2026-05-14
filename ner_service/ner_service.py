import os
import sys

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
from common.logger import log_event

ner_bp = Blueprint('ner', __name__)

@ner_bp.route('/extract', methods=['POST'])
def extract():
    """
    Extract entities from text (Placeholder)
    ---
    tags:
      - NER
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            text:
              type: string
              example: "Surat dari Budi tanggal 12 Juni"
    responses:
      200:
        description: Entities extracted
    """
    log_event("ner_service", "Extraction request received")
    data = request.json
    text = data.get("text", "")

    # Placeholder logic (Nanti diganti dengan model NER lokal Anda)
    entities = {
        "names": [],
        "dates": [],
        "locations": []
    }
    
    log_event("ner_service", "Extraction successful (placeholder)")
    return jsonify(entities), 200

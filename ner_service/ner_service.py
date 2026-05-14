from flask import Blueprint, jsonify, request
from common.logger import log_event
from transformers import pipeline

# Load NER Pipeline menggunakan IndoBERT
try:
    log_event("ner_service", "Loading IndoBERT NER model...")
    # Model cahya/bert-base-indonesian-NER sangat bagus untuk Nama, Lokasi, dan Organisasi di teks Indonesia
    ner_pipeline = pipeline(
        "ner", 
        model="cahya/bert-base-indonesian-NER", 
        aggregation_strategy="simple" # Penting agar kata tidak terpotong (menghilangkan ##)
    )
    log_event("ner_service", "IndoBERT NER model loaded successfully")
except Exception as e:
    log_event("ner_service", f"Failed to load NER model: {str(e)}")
    ner_pipeline = None

ner_bp = Blueprint('ner', __name__)

@ner_bp.route('/extract', methods=['POST'])
def extract_entities():
    """
    Extract entities from text using IndoBERT
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
              example: "Bima Sunu adalah mahasiswa dari Tegal."
    responses:
      200:
        description: List of extracted entities
        schema:
          type: object
          properties:
            names:
              type: array
              items:
                type: string
            locations:
              type: array
              items:
                type: string
            dates:
              type: array
              items:
                type: string
            others:
              type: array
              items:
                type: string
      400:
        description: No text provided
    """
    data = request.json
    text = data.get('text', '')
    
    if not text:
        return jsonify({"error": "No text provided"}), 400

    if not ner_pipeline:
        # Fallback jika model gagal load
        return jsonify({"names": [], "locations": [], "dates": [], "others": []}), 200

    try:
        entities = ner_pipeline(text)
        
        result = {
            "names": [],
            "locations": [],
            "dates": [],
            "others": []
        }
        
        for ent in entities:
            # cahya/bert-base-indonesian-NER-1 menggunakan label: PER, LOC, ORG
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
            
        # Catatan: Model BERT ini tidak fokus pada DATE. 
            
        log_event("ner_service", f"Extraction successful: {len(entities)} entities found")
        return jsonify(result), 200
    except Exception as e:
        log_event("ner_service", f"Extraction failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

@ner_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "ner_service"}), 200

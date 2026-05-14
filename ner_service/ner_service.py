from flask import Blueprint, jsonify, request
from common.logger import log_event
from transformers import pipeline

# Load NER Pipeline
try:
    log_event("ner_service", "Loading NER model...")
    # Model ini bagus untuk mendeteksi Orang (PER), Lokasi (LOC), dan Organisasi (ORG)
    ner_pipeline = pipeline("ner", model="dbmdz/bert-large-cased-finetuned-conll03-english", aggregation_strategy="simple")
    log_event("ner_service", "NER model loaded successfully")
except Exception as e:
    log_event("ner_service", f"Failed to load NER model: {str(e)}")
    ner_pipeline = None

ner_bp = Blueprint('ner', __name__)

@ner_bp.route('/extract', methods=['POST'])
def extract_entities():
    """
    Extract entities from text using Transformers
    ---
    tags:
      - NER
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
            label = ent['entity_group']
            word = ent['word']
            
            if label == 'PER':
                result['names'].append(word)
            elif label == 'LOC':
                result['locations'].append(word)
            elif label == 'ORG':
                result['others'].append(f"ORG: {word}")
            
        # Catatan: Model BERT ini tidak fokus pada DATE. 
        # Kita bisa menambahkan deteksi tanggal sederhana atau model lain nanti.
            
        log_event("ner_service", f"Extraction successful: {len(entities)} entities found")
        return jsonify(result), 200
    except Exception as e:
        log_event("ner_service", f"Extraction failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

@ner_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "ner_service"}), 200

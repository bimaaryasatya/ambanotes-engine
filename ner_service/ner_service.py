import os
import sys
import re
import json
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify, current_app
from common.logger import log_event
from common.jwt_utils import token_required
from common.config import Config
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


def parse_json_markdown(text):
    """Strip markdown code blocks and parse JSON."""
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        text = match.group(1)
    text = text.strip()
    return json.loads(text)


def _extract_mistral(text):
    """Extract entities using Mistral API with instruction prompt."""
    prompt = f"""
    Ekstrak entitas bernama (Named Entity Recognition) dari teks surat berikut ke dalam format JSON yang valid.
    
    Kategori entitas yang harus diekstrak:
    1. names: Daftar nama-nama orang yang disebutkan di dalam teks (array of strings).
    2. locations: Daftar nama-nama tempat, kota, negara, atau lokasi (array of strings).
    3. dates: Daftar tanggal-tanggal yang disebutkan di dalam teks (array of strings).
    4. others: Entitas lain yang relevan seperti nama organisasi, jabatan, atau entitas penting lainnya (array of strings). Untuk organisasi, gunakan format "ORG: [Nama Organisasi]".
    5. nomor_surat: Nomor surat resmi yang tertera di dalam teks (string, berikan string kosong jika tidak ditemukan).
    6. perihal: Perihal atau subjek dari surat tersebut (string, berikan string kosong jika tidak ditemukan).
    7. organisasi_penerbit: Nama organisasi, instansi, atau perusahaan yang menerbitkan/mengirimkan surat tersebut (string, berikan string kosong jika tidak ditemukan).
    
    Format output harus berupa JSON objek valid dengan kunci-kunci di atas tanpa penjelasan atau komentar tambahan.
    
    Teks Surat:
    {text}
    """
    
    headers = {
        "Authorization": f"Bearer {Config.MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "mistral-large-latest",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }
    
    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30
    )
    response.raise_for_status()
    content = response.json()['choices'][0]['message']['content'].strip()
    
    try:
        extracted = parse_json_markdown(content)
    except Exception:
        extracted = json.loads(content)
        
    # Ensure all fields exist and are of correct type
    result = {
        "names": list(extracted.get("names", [])),
        "locations": list(extracted.get("locations", [])),
        "dates": list(extracted.get("dates", [])),
        "others": list(extracted.get("others", [])),
        "nomor_surat": str(extracted.get("nomor_surat", "")),
        "perihal": str(extracted.get("perihal", "")),
        "organisasi_penerbit": str(extracted.get("organisasi_penerbit", ""))
    }
    return result


@ner_bp.route('/extract', methods=['POST'])
@token_required
def extract_entities(current_user):
    """
    Extract entities from text using IndoBERT or Mistral LLM
    ---
    tags:
      - NER
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
              example: "Bima Sunu adalah mahasiswa dari Tegal."
            mode:
              type: string
              enum: [local, mistral]
              default: local
              description: Pilih mode ekstraksi NER (local/IndoBERT atau online Mistral)
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

    data = request.get_json(force=True, silent=True) or {}
    text = data.get('text', '')
    
    # Mode toggle: check request parameter first, then default from current_app.config, fallback to 'local'
    default_mode = current_app.config.get('NER_DEFAULT_MODE', 'local').lower()
    mode = data.get('mode', default_mode).lower()

    if not text:
        return jsonify({"error": "No text provided"}), 400

    log_event("ner_service", f"Extract request ({mode}) from: {current_user.get('username')}",
              user_id=user_id, org_id=org_id, action="NER_EXTRACT_START", metadata={"mode": mode})

    # Prepare standard empty result
    empty_result = {
        "names": [],
        "locations": [],
        "dates": [],
        "others": [],
        "nomor_surat": "",
        "perihal": "",
        "organisasi_penerbit": ""
    }

    if mode == 'mistral':
        try:
            result = _extract_mistral(text)
            log_event("ner_service", f"Extraction successful (mistral)",
                      user_id=user_id, org_id=org_id, action="NER_SUCCESS", metadata={"mode": mode})
            return jsonify(result), 200
        except Exception as e:
            log_event("ner_service", f"Mistral extraction failed ({str(e)}). Falling back to local/IndoBERT.",
                      user_id=user_id, org_id=org_id, action="NER_AUTO_FALLBACK_LOCAL", metadata={"error": str(e)})

    # Local IndoBERT mode (default or fallback)
    if not ner_pipeline:
        return jsonify(empty_result), 200

    try:
        entities = ner_pipeline(text)

        result = {
            "names": [],
            "locations": [],
            "dates": [],
            "others": [],
            "nomor_surat": "",
            "perihal": "",
            "organisasi_penerbit": ""
        }

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

        log_event("ner_service", f"Extraction successful (local): {len(entities)} entities found",
                  user_id=user_id, org_id=org_id, action="NER_SUCCESS", metadata={"entity_count": len(entities), "mode": "local"})
        return jsonify(result), 200
    except Exception as e:
        log_event("ner_service", f"Extraction failed (local): {str(e)}",
                  user_id=user_id, org_id=org_id, action="NER_FAILED", metadata={"error": str(e)}, severity="error")
        return jsonify({"error": "Extraction failed"}), 500


@ner_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "ner_service",
        "local_model_loaded": ner_pipeline is not None
    }), 200


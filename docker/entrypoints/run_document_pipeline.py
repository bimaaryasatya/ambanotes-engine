import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(BASE_DIR)

from flask import Flask, jsonify
from flask_cors import CORS

from document_service.document_service import document_bp
from classification_service.classification_service import classification_bp
from ner_service.ner_service import ner_bp
from ocr_service.ocr_service import ocr_bp
from common.logger import log_event

app = Flask(__name__)
CORS(app)
app.config['NER_DEFAULT_MODE'] = 'mistral'

app.register_blueprint(document_bp, url_prefix='/document')
app.register_blueprint(classification_bp, url_prefix='/classification')
app.register_blueprint(ner_bp, url_prefix='/ner')
app.register_blueprint(ocr_bp, url_prefix='/ocr')

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "document_pipeline"}), 200

if __name__ == '__main__':
    log_event("document_pipeline", "Starting Document Pipeline (Docker)", action="PIPELINE_START")
    app.run(host='0.0.0.0', port=5001, debug=True)

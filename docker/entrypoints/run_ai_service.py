import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(BASE_DIR)

from flask import Flask, jsonify
from flask_cors import CORS

from ai_service.ai_service import ai_bp
from common.logger import log_event

app = Flask(__name__)
CORS(app)

app.register_blueprint(ai_bp, url_prefix='/ai')

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "ai_service"}), 200

if __name__ == '__main__':
    log_event("ai_service", "Starting AI Service (Docker)", action="AI_START")
    app.run(host='0.0.0.0', port=5002, debug=True)

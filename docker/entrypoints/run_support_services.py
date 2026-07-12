import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(BASE_DIR)

from flask import Flask, jsonify, render_template_string
from flask_cors import CORS

from generator_service.generator import (
    generator_bp,
    build_verification_result,
    PUBLIC_VERIFY_TEMPLATE,
)
from notification_service.notif import notification_bp
from reminder_service.reminder import reminder_bp
from insight_service.insight_service import insight_bp
from common.logger import log_event

app = Flask(__name__)
CORS(app)

app.register_blueprint(generator_bp, url_prefix='/generator')
app.register_blueprint(notification_bp, url_prefix='/notification')
app.register_blueprint(reminder_bp, url_prefix='/reminder')
app.register_blueprint(insight_bp, url_prefix='/insight')

@app.route('/verify/<doc_hash>', methods=['GET'])
def public_verify_document(doc_hash):
    result = build_verification_result(doc_hash)
    status_code = 200 if result["valid"] else 404
    return render_template_string(PUBLIC_VERIFY_TEMPLATE, **result), status_code

@app.route('/verify/<doc_hash>/json', methods=['GET'])
def public_verify_document_json(doc_hash):
    result = build_verification_result(doc_hash)
    status_code = 200 if result["valid"] else 404
    return jsonify(result), status_code

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "support_services"}), 200

if __name__ == '__main__':
    log_event("support_services", "Starting Support Services (Docker)", action="SUPPORT_START")
    app.run(host='0.0.0.0', port=5003, debug=True)

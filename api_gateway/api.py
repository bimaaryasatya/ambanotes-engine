import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from flask import Flask, jsonify
from flask_cors import CORS
from flasgger import Swagger
from common.logger import log_event

# Import Blueprints
from classification_service.classification_service import classification_bp
from insight_service.insight_service import insight_bp
from ner_service.ner_service import ner_bp
from reminder_service.reminder import reminder_bp
from ocr_service.ocr_service import ocr_bp
from auth_service.auth_service import auth_bp
from document_service.document_service import document_bp
from notification_service.notif import notification_bp
from ai_service.ai_service import ai_bp
from generator_service.generator import generator_bp

app = Flask(__name__)
CORS(app)

# Configure Swagger
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec',
            "route": '/apispec.json',
            "rule_filter": lambda rule: True,  # all in
            "model_filter": lambda tag: True,  # all in
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
    "uiversion": 3,
    "openapi": "3.0.1",
}

swagger_template = {
    "securityDefinitions": {
        "BearerAuth": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "Masukkan token JWT dengan format: **Bearer &lt;token&gt;**"
        }
    }
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

# Register Blueprints with url prefixes
app.register_blueprint(classification_bp, url_prefix='/classification')
app.register_blueprint(insight_bp, url_prefix='/insight')
app.register_blueprint(ner_bp, url_prefix='/ner')
app.register_blueprint(reminder_bp, url_prefix='/reminder')
app.register_blueprint(ocr_bp, url_prefix='/ocr')
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(document_bp, url_prefix='/document')
app.register_blueprint(notification_bp, url_prefix='/notification')
app.register_blueprint(ai_bp, url_prefix='/ai')
app.register_blueprint(generator_bp, url_prefix='/generator')

@app.route('/', methods=['GET'])
def index():
    return jsonify({"message": "AmbaNotes API Gateway: Server is running"}), 200

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health Check Endpoint (Gateway)
    ---
    tags:
      - Gateway
    responses:
      200:
        description: API Gateway is healthy
    """
    log_event("api_gateway", "Gateway health check requested", action="HEALTH_CHECK")
    return jsonify({"status": "healthy", "service": "api_gateway"}), 200

if __name__ == '__main__':
    log_event("api_gateway", "Starting Unified API Gateway", action="GATEWAY_START")
    # Run all services on a single port
    app.run(host='0.0.0.0', port=5009, debug=True)

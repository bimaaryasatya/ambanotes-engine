import os
import sys

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify
from common.logger import log_event

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health Check Endpoint (Auth)
    ---
    tags:
      - Auth
    responses:
      200:
        description: Service is healthy
    """
    log_event("auth_service", "Health check requested")
    return jsonify({"status": "healthy", "service": "auth_service"}), 200
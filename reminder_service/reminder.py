import os
import sys

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify
from common.logger import log_event

reminder_bp = Blueprint('reminder', __name__)

@reminder_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health Check Endpoint (Reminder)
    ---
    tags:
      - Reminder
    responses:
      200:
        description: Service is healthy
    """
    log_event("reminder_service", "Health check requested", action="HEALTH_CHECK")
    return jsonify({"status": "healthy", "service": "reminder_service"}), 200

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify
from insight_service.services.analytics_service import generate_insight
from common.logger import log_event
from common.jwt_utils import token_required

insight_bp = Blueprint('insight', __name__)


@insight_bp.route("/")
def home():
    """
    Insight Home Endpoint
    ---
    tags:
      - Insight
    responses:
      200:
        description: Welcome message
    """
    return jsonify({"message": "Instagram Event Insight API"})


@insight_bp.route("/api/insights", methods=["GET"])
@token_required
def insights(current_user):
    """
    Get Instagram Event Insights
    ---
    tags:
      - Insight
    security:
      - BearerAuth: []
    responses:
      200:
        description: Detailed insights from Instagram data
      401:
        description: Unauthorized
      500:
        description: Internal Server Error
    """
    log_event("insight_service", f"Insights requested by: {current_user.get('username')}")
    try:
        data = generate_insight()
        return jsonify(data), 200
    except Exception as e:
        log_event("insight_service", f"Failed to generate insights: {str(e)}")
        return jsonify({"error": str(e)}), 500
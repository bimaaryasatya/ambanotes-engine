import os
import sys

# Add parent directory to path so we can import from common if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify
from insight_service.services.analytics_service import generate_insight
from common.logger import log_event

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
        schema:
          type: object
          properties:
            message:
              type: string
              example: Instagram Event Insight API
    """
    log_event("insight_service", "Home endpoint accessed")
    return jsonify({
        "message": "Instagram Event Insight API"
    })

@insight_bp.route("/api/insights", methods=["GET"])
def insights():
    """
    Get Instagram Event Insights
    ---
    tags:
      - Insight
    responses:
      200:
        description: Detailed insights from Instagram data
        schema:
          type: object
          properties:
            total_posts:
              type: integer
              example: 150
            top_accounts:
              type: object
              additionalProperties:
                type: integer
              example: {"account1": 20, "account2": 15}
            likes_distribution:
              type: object
              properties:
                min:
                  type: integer
                  example: 5
                max:
                  type: integer
                  example: 500
                avg:
                  type: number
                  example: 120.5
            most_active_day:
              type: object
              additionalProperties:
                type: integer
              example: {"Monday": 30, "Friday": 45}
            event_trends:
              type: object
              additionalProperties:
                type: integer
              example: {"Natal": 25, "Worship": 40}
      500:
        description: Internal Server Error
        schema:
          type: object
          properties:
            error:
              type: string
              example: "Something went wrong"
    """
    log_event("insight_service", "Fetching insights")
    try:
        data = generate_insight()
        log_event("insight_service", "Insights generated successfully")
        return jsonify(data), 200

    except Exception as e:
        log_event("insight_service", f"Failed to generate insights: {str(e)}")
        return jsonify({
            "error": str(e)
        }), 500
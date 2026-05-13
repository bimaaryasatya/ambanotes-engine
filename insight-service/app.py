from flask import Flask, jsonify
from flask_cors import CORS
from flasgger import Swagger
from services.analytics_service import generate_insight

app = Flask(__name__)
CORS(app)
swagger = Swagger(app)

@app.route("/")
def home():
    """
    Home Endpoint
    ---
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
    return jsonify({
        "message": "Instagram Event Insight API"
    })

@app.route("/api/insights", methods=["GET"])
def insights():
    """
    Get Instagram Event Insights
    ---
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
    try:
        data = generate_insight()
        return jsonify(data), 200

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5005,
        debug=True
    )
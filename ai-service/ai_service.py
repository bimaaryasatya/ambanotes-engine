from flask import Flask, request, jsonify
import requests
from common.config import Config

app = Flask(__name__)

@app.route("/process", methods=["POST"])
def process():
    text = request.json["text"]

    prompt = f"""
    Analisa dokumen berikut:
    1. Klasifikasi
    2. Ringkasan
    3. Entity (nama, tanggal, nominal)

    Text:
    {text}
    """

    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {Config.MISTRAL_API_KEY}"},
        json={
            "model": "mistral-small",
            "messages": [{"role": "user", "content": prompt}]
        }
    )

    result = response.json()

    return jsonify({
        "classification": result,
        "summary": result,
        "entities": result
    })
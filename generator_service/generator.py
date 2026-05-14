import os
import sys
import datetime
from bson import ObjectId

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify, render_template_string
from common.logger import log_event
from common.jwt_utils import token_required
from common.db import users_col, delegations_col, assets_col

generator_bp = Blueprint('generator', __name__)

# --- HTML Template for Surat Tugas ---
SURAT_TUGAS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: "Times New Roman", Times, serif; line-height: 1.6; margin: 40px; }
        .kop-surat { text-align: center; border-bottom: 3px solid black; padding-bottom: 10px; margin-bottom: 20px; }
        .kop-img { max-width: 100%; height: auto; }
        .title { text-align: center; text-decoration: underline; font-weight: bold; font-size: 18px; margin-bottom: 5px; }
        .nomor { text-align: center; margin-bottom: 30px; }
        .content { margin-bottom: 20px; }
        .footer { margin-top: 50px; float: right; width: 300px; text-align: center; }
        .signature-img { max-width: 150px; margin: 10px 0; }
        .clear { clear: both; }
    </style>
</head>
<body>
    <div class="kop-surat">
        {% if letterhead %}
            <img src="{{ letterhead }}" class="kop-img">
        {% else %}
            <h2>{{ delegation_name }}</h2>
            <p>{{ org_name }}</p>
        {% endif %}
    </div>

    <div class="title">SURAT TUGAS</div>
    <div class="nomor">Nomor: {{ doc_number }}</div>

    <div class="content">
        <p>Yang bertanda tangan di bawah ini menerangkan bahwa:</p>
        <p style="margin-left: 20px;"><strong>{{ task_description }}</strong></p>
        
        <p>Demikian surat tugas ini dibuat untuk dapat dipergunakan sebagaimana mestinya.</p>
    </div>

    <div class="footer">
        <p>{{ city }}, {{ current_date }}</p>
        <p>Hormat Kami,</p>
        {% if signature %}
            <img src="{{ signature }}" class="signature-img">
        {% else %}
            <div style="height: 80px;"></div>
        {% endif %}
        <p><strong>( {{ signatory_name }} )</strong></p>
    </div>
    <div class="clear"></div>
</body>
</html>
"""

@generator_bp.route('/surat-tugas', methods=['POST'])
@token_required
def generate_surat_tugas(current_user):
    """
    Generate Surat Tugas (HTML Template)
    ---
    tags:
      - Generator
    security:
      - BearerAuth: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - doc_number
            - task_description
            - signatory_name
          properties:
            doc_number:
              type: string
              example: "001/ST/2026"
            task_description:
              type: string
              example: "Melaksanakan koordinasi lapangan terkait proyek jalan."
            signatory_name:
              type: string
              example: "Bima Arya Satya"
            city:
              type: string
              default: "Jakarta"
    responses:
      200:
        description: Generated HTML string
    """
    user_id = current_user.get('user_id')
    org_id = current_user.get('org_id')
    
    data = request.json or {}
    doc_number = data.get('doc_number')
    task_description = data.get('task_description')
    signatory_name = data.get('signatory_name')
    city = data.get('city', 'Jakarta')
    
    if not doc_number or not task_description or not signatory_name:
        return jsonify({"error": "Missing required fields"}), 400

    # 1. Fetch User and Delegation
    user = users_col.find_one({"_id": ObjectId(user_id)})
    delegation_id = user.get('delegation_id')
    
    if not delegation_id:
        return jsonify({"error": "User does not have an assigned delegation"}), 403
    
    delegation = delegations_col.find_one({"_id": ObjectId(delegation_id)})
    delegation_name = delegation.get('name') if delegation else "Unknown Unit"

    # 2. Fetch Assets (Kop & TTD)
    letterhead_asset = assets_col.find_one({"type": "letterhead", "delegation_id": delegation_id})
    signature_asset = assets_col.find_one({"type": "signature", "delegation_id": delegation_id})
    
    letterhead_url = letterhead_asset.get('image_data') if letterhead_asset else None
    signature_url = signature_asset.get('image_data') if signature_asset else None

    # 3. Render HTML
    html_content = render_template_string(
        SURAT_TUGAS_TEMPLATE,
        doc_number=doc_number,
        task_description=task_description,
        signatory_name=signatory_name,
        delegation_name=delegation_name,
        letterhead=letterhead_url,
        signature=signature_url,
        city=city,
        current_date=datetime.date.today().strftime("%d %B %Y")
    )

    log_event("generator_service", f"Surat Tugas generated for {delegation_name}", 
              user_id=user_id, org_id=org_id, action="GENERATE_SURAT_TUGAS")

    return jsonify({
        "html": html_content,
        "message": "HTML template generated successfully. Use a PDF library on frontend/backend to convert."
    }), 200


@generator_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "generator_service"}), 200

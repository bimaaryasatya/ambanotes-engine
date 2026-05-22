import os
import sys
import datetime
from bson import ObjectId

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify, render_template_string
from common.logger import log_event
from common.jwt_utils import token_required
from common.db import users_col, delegations_col, assets_col, docs_col, orgs_col
import hashlib

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
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - BearerAuth: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: "Format: Bearer <token>"
        default: "Bearer "
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
    try:
        user_id = current_user.get('user_id')
        org_id = current_user.get('org_id')
        
        data = request.get_json(force=True, silent=True) or {}
        
        # 1. Fetch User and Delegation/Organization name
        user = users_col.find_one({"_id": ObjectId(user_id)})
        delegation_id = user.get('delegation_id') if user else None
        
        org = orgs_col.find_one({"_id": ObjectId(org_id)}) if org_id else None
        org_name = org.get('name') if org else "Personal Workspace"
        
        delegation_name = org_name
        if delegation_id:
            try:
                delegation = delegations_col.find_one({"_id": ObjectId(delegation_id)})
                if delegation:
                    delegation_name = delegation.get('name')
            except Exception:
                pass

        doc_number = data.get('doc_number') or data.get('letter_number')
        signatory_name = data.get('signatory_name') or (user.get('username') if user else 'Kepala Instansi')
        
        task_description = data.get('task_description')
        if not task_description:
            ref_doc_id = data.get('reference_doc_id')
            ref_title = "Undangan"
            if ref_doc_id:
                ref_doc = docs_col.find_one({"doc_id": ref_doc_id})
                if not ref_doc:
                    try:
                        ref_doc = docs_col.find_one({"_id": ObjectId(ref_doc_id)})
                    except Exception:
                        pass
                if ref_doc:
                    entities = ref_doc.get('entities', {})
                    ref_title = entities.get('perihal') or entities.get('subject') or ref_doc.get('filename', 'Undangan')
            
            date_str = data.get('date', datetime.date.today().strftime("%d %B %Y"))
            time_str = data.get('time', '09:00 WIB')
            location_str = data.get('location', 'Kantor Pusat')
            task_description = f"Menghadiri dan berpartisipasi aktif dalam kegiatan '{ref_title}' yang diselenggarakan pada tanggal {date_str} pukul {time_str} berlokasi di {location_str}."

        city = data.get('city', 'Jakarta')
        
        if not doc_number or not task_description or not signatory_name:
            return jsonify({"error": "Missing required fields (doc_number/letter_number, task_description, signatory_name)"}), 400

        # 2. Fetch Assets (Kop & TTD) by name or fallback
        kop_name = data.get('kop')
        ttd_name = data.get('ttd')
        
        letterhead_asset = None
        if kop_name:
            letterhead_asset = assets_col.find_one({"type": "letterhead", "org_id": org_id, "name": kop_name, "is_active": {"$ne": False}})
            
        if not letterhead_asset:
            if delegation_id:
                try:
                    letterhead_asset = assets_col.find_one({"type": "letterhead", "delegation_id": delegation_id, "is_active": {"$ne": False}})
                except Exception:
                    pass
            if not letterhead_asset:
                letterhead_asset = assets_col.find_one({"type": "letterhead", "org_id": org_id, "is_active": {"$ne": False}})

        signature_asset = None
        if ttd_name:
            signature_asset = assets_col.find_one({"type": "signature", "org_id": org_id, "name": ttd_name, "is_active": {"$ne": False}})
            
        if not signature_asset:
            if delegation_id:
                try:
                    signature_asset = assets_col.find_one({"type": "signature", "delegation_id": delegation_id, "is_active": {"$ne": False}})
                except Exception:
                    pass
            if not signature_asset:
                signature_asset = assets_col.find_one({"type": "signature", "org_id": org_id, "is_active": {"$ne": False}})
        
        letterhead_url = letterhead_asset.get('image_data') if letterhead_asset else None
        signature_url = signature_asset.get('image_data') if signature_asset else None

        # 3. Render HTML
        html_content = render_template_string(
            SURAT_TUGAS_TEMPLATE,
            doc_number=doc_number,
            task_description=task_description,
            signatory_name=signatory_name,
            delegation_name=delegation_name,
            org_name=org_name,
            letterhead=letterhead_url,
            signature=signature_url,
            city=city,
            current_date=datetime.date.today().strftime("%d %B %Y")
        )

        # 4. Generate Unique Hash for Anti-Fraud
        doc_hash = hashlib.sha256(f"{user_id}{datetime.datetime.utcnow().timestamp()}".encode()).hexdigest()[:16]
        
        # Store reference in docs_col (or a dedicated collection)
        docs_col.update_one(
            {"doc_id": doc_number}, # Using doc_number as a unique ref here
            {"$set": {
                "doc_id": doc_number,
                "filename": f"SURAT_TUGAS_{doc_number}.pdf",
                "content": task_description,
                "org_id": org_id,
                "verification_hash": doc_hash,
                "is_generated": True,
                "created_at": datetime.datetime.utcnow()
            }},
            upsert=True
        )

        log_event("generator_service", f"Surat Tugas generated for {delegation_name}", 
                  user_id=user_id, org_id=org_id, action="GENERATE_SURAT_TUGAS", metadata={"hash": doc_hash})

        return jsonify({
            "html": html_content,
            "verification_hash": doc_hash,
            "message": "HTML template generated successfully. Use the hash to verify authenticity."
        }), 200
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        log_event("generator_service", f"Error generating Surat Tugas: {str(e)}", 
                  user_id=current_user.get('user_id'), org_id=current_user.get('org_id'), 
                  action="GENERATE_SURAT_TUGAS_ERROR", metadata={"error": error_details})
        print(f"DEBUG ERROR in generate_surat_tugas:\n{error_details}")
        return jsonify({
            "error": "Internal Server Error during Surat Tugas generation",
            "details": str(e),
            "traceback": error_details
        }), 500


@generator_bp.route('/verify/<doc_hash>', methods=['GET'])
def verify_document(doc_hash):
    """
    Verify Document Authenticity (Anti-Fraud)
    ---
    tags:
      - Generator
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: doc_hash
        in: path
        type: string
        required: true
    responses:
      200:
        description: Verification status
    """
    doc = docs_col.find_one({"verification_hash": doc_hash})
    if not doc:
        return jsonify({"valid": False, "message": "Document hash not found. This might be a forgery."}), 404
    
    return jsonify({
        "valid": True,
        "message": "Document is AUTHENTIC",
        "details": {
            "doc_id": doc['doc_id'],
            "org_id": doc['org_id'],
            "created_at": doc['created_at'].isoformat() if 'created_at' in doc else None
        }
    }), 200


@generator_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "generator_service"}), 200

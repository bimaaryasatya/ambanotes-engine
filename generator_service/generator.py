import os
import sys
import re
import io
import uuid
import json
import base64
import hashlib
import datetime
import requests
from bson import ObjectId
from PIL import Image, ImageDraw, ImageFont

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify, render_template_string
from common.logger import log_event
from common.jwt_utils import token_required, role_required
from common.db import users_col, delegations_col, assets_col, docs_col, orgs_col
from common.google_drive_client import upload_file_to_google_drive

generator_bp = Blueprint('generator', __name__)


SURAT_TUGAS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: "Times New Roman", Times, serif; line-height: 1.65; margin: 36px; color: #111; }
        .kop-surat { text-align: center; border-bottom: 3px solid black; padding-bottom: 12px; margin-bottom: 24px; }
        .kop-img { max-width: 100%; height: auto; }
        .title { text-align: center; text-decoration: underline; font-weight: bold; font-size: 20px; margin-bottom: 4px; }
        .nomor { text-align: center; margin-bottom: 26px; }
        .content { margin-bottom: 18px; }
        .task-box { margin: 16px 0; padding: 12px 14px; border: 1px solid #222; }
        .footer { margin-top: 52px; float: right; width: 280px; text-align: center; }
        .signature-img { max-width: 150px; max-height: 90px; margin: 10px 0; }
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
        <p>Yang bertanda tangan di bawah ini memberikan penugasan kepada pihak terkait untuk melaksanakan kegiatan sebagai berikut:</p>
        <div class="task-box">
            <strong>{{ task_description }}</strong>
        </div>
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


def _safe_object_id(value):
    try:
        return ObjectId(value)
    except Exception:
        return value


def _format_indonesian_date(date_obj=None):
    date_obj = date_obj or datetime.date.today()
    months = [
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    ]
    return f"{date_obj.day:02d} {months[date_obj.month - 1]} {date_obj.year}"


def _sanitize_filename_component(value):
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '_', (value or '').strip())
    cleaned = cleaned.strip('._')
    return cleaned or 'surat_tugas'


def _find_user(user_id):
    user = users_col.find_one({"_id": _safe_object_id(user_id)})
    if not user:
        user = users_col.find_one({"_id": user_id})
    return user


def _find_org(org_id):
    return orgs_col.find_one({"_id": _safe_object_id(org_id)})


def _resolve_delegation_name(org_id, delegation_id):
    if not delegation_id or delegation_id == 'general':
        return 'General'

    delegation = delegations_col.find_one({
        "_id": _safe_object_id(delegation_id),
        "org_id": org_id,
    })
    if not delegation:
        delegation = delegations_col.find_one({
            "_id": delegation_id,
            "org_id": org_id,
        })
    return delegation.get('name') if delegation else 'General'


def _find_reference_doc(reference_doc_id, org_id):
    if not reference_doc_id:
        return None

    doc = docs_col.find_one({"doc_id": reference_doc_id, "org_id": org_id})
    if doc:
        return doc

    try:
        return docs_col.find_one({"_id": ObjectId(reference_doc_id), "org_id": org_id})
    except Exception:
        return None


def _get_asset(org_id, delegation_id, asset_name, asset_types):
    if asset_name:
        asset = assets_col.find_one({
            "org_id": org_id,
            "name": asset_name,
            "type": {"$in": asset_types},
            "is_active": {"$ne": False},
        })
        if asset:
            return asset

    if delegation_id and delegation_id != 'general':
        asset = assets_col.find_one({
            "delegation_id": {"$in": [delegation_id, _safe_object_id(delegation_id)]},
            "type": {"$in": asset_types},
            "is_active": {"$ne": False},
        })
        if asset:
            return asset

    return assets_col.find_one({
        "org_id": org_id,
        "type": {"$in": asset_types},
        "is_active": {"$ne": False},
    })


def _load_image_from_value(value):
    if not value:
        return None

    try:
        if isinstance(value, bytes):
            return Image.open(io.BytesIO(value)).convert("RGBA")

        raw = str(value).strip()
        if not raw:
            return None

        if raw.startswith('http://') or raw.startswith('https://'):
            res = requests.get(raw, timeout=15)
            if res.status_code == 200:
                return Image.open(io.BytesIO(res.content)).convert("RGBA")
            return None

        if raw.startswith('data:image'):
            raw = raw.split(',', 1)[1]

        padded = raw + ('=' * ((4 - len(raw) % 4) % 4))
        decoded = base64.b64decode(padded)
        return Image.open(io.BytesIO(decoded)).convert("RGBA")
    except Exception:
        return None


def _get_font(size, bold=False):
    font_candidates = []
    if bold:
        font_candidates.extend([
            "C:/Windows/Fonts/timesbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
        ])
    else:
        font_candidates.extend([
            "C:/Windows/Fonts/times.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
        ])

    for path in font_candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


def _wrap_text(draw, text, font, max_width):
    words = (text or '').split()
    if not words:
        return ['']

    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        width = draw.textbbox((0, 0), trial, font=font)[2]
        if width <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_wrapped_paragraph(draw, text, font, x, y, max_width, line_gap=10, fill=(20, 20, 20)):
    line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + line_gap
    for line in _wrap_text(draw, text, font, max_width):
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def _render_assignment_pdf_bytes(payload, letterhead_image, signature_image):
    page_width = 1240
    page_height = 1754
    margin_x = 90
    cursor_y = 70
    usable_width = page_width - (margin_x * 2)

    page = Image.new("RGB", (page_width, page_height), "white")
    draw = ImageDraw.Draw(page)

    title_font = _get_font(36, bold=True)
    subtitle_font = _get_font(24, bold=False)
    body_font = _get_font(28, bold=False)
    body_bold_font = _get_font(28, bold=True)
    small_font = _get_font(24, bold=False)

    if letterhead_image:
        max_header_height = 230
        ratio = min(usable_width / letterhead_image.width, max_header_height / letterhead_image.height)
        ratio = min(ratio, 1.0)
        resized = letterhead_image.resize(
            (max(1, int(letterhead_image.width * ratio)), max(1, int(letterhead_image.height * ratio)))
        )
        header_x = (page_width - resized.width) // 2
        page.paste(resized, (header_x, cursor_y), resized)
        cursor_y += resized.height + 20
    else:
        org_text = payload['org_name']
        del_text = payload['delegation_name']
        org_box = draw.textbbox((0, 0), del_text, font=title_font)
        draw.text(((page_width - (org_box[2] - org_box[0])) / 2, cursor_y), del_text, font=title_font, fill=(0, 0, 0))
        cursor_y += 48
        org_sub_box = draw.textbbox((0, 0), org_text, font=subtitle_font)
        draw.text(((page_width - (org_sub_box[2] - org_sub_box[0])) / 2, cursor_y), org_text, font=subtitle_font, fill=(0, 0, 0))
        cursor_y += 42

    draw.line((margin_x, cursor_y, page_width - margin_x, cursor_y), fill=(0, 0, 0), width=3)
    cursor_y += 42

    title = "SURAT TUGAS"
    title_box = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((page_width - (title_box[2] - title_box[0])) / 2, cursor_y), title, font=title_font, fill=(0, 0, 0))
    cursor_y += 56

    number_text = f"Nomor: {payload['doc_number']}"
    number_box = draw.textbbox((0, 0), number_text, font=subtitle_font)
    draw.text(((page_width - (number_box[2] - number_box[0])) / 2, cursor_y), number_text, font=subtitle_font, fill=(0, 0, 0))
    cursor_y += 78

    intro = "Yang bertanda tangan di bawah ini memberikan penugasan kepada pihak terkait untuk melaksanakan kegiatan sebagai berikut:"
    cursor_y = _draw_wrapped_paragraph(draw, intro, body_font, margin_x, cursor_y, usable_width)
    cursor_y += 18

    box_top = cursor_y
    text_x = margin_x + 28
    text_y = box_top + 24
    wrapped_task_lines = _wrap_text(draw, payload['task_description'], body_bold_font, usable_width - 56)
    line_height = draw.textbbox((0, 0), "Ag", font=body_bold_font)[3] + 12
    box_height = max(120, 34 + (len(wrapped_task_lines) * line_height))
    draw.rounded_rectangle(
        (margin_x, box_top, page_width - margin_x, box_top + box_height),
        radius=18,
        outline=(0, 0, 0),
        width=2,
    )
    for line in wrapped_task_lines:
        draw.text((text_x, text_y), line, font=body_bold_font, fill=(0, 0, 0))
        text_y += line_height
    cursor_y = box_top + box_height + 30

    closing = "Demikian surat tugas ini dibuat untuk dapat dipergunakan sebagaimana mestinya."
    cursor_y = _draw_wrapped_paragraph(draw, closing, body_font, margin_x, cursor_y, usable_width)
    cursor_y += 60

    footer_x = page_width - 420
    draw.text((footer_x, cursor_y), f"{payload['city']}, {payload['current_date']}", font=small_font, fill=(0, 0, 0))
    cursor_y += 42
    draw.text((footer_x + 24, cursor_y), "Hormat Kami,", font=small_font, fill=(0, 0, 0))
    cursor_y += 34

    if signature_image:
        max_signature_width = 200
        max_signature_height = 110
        ratio = min(max_signature_width / signature_image.width, max_signature_height / signature_image.height, 1.0)
        resized = signature_image.resize(
            (max(1, int(signature_image.width * ratio)), max(1, int(signature_image.height * ratio)))
        )
        page.paste(resized, (footer_x + 24, cursor_y), resized)
        cursor_y += resized.height + 24
    else:
        cursor_y += 110

    draw.text((footer_x, cursor_y), f"( {payload['signatory_name']} )", font=body_bold_font, fill=(0, 0, 0))

    pdf_buffer = io.BytesIO()
    page.save(pdf_buffer, format="PDF", resolution=150.0)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


def _build_task_description(data, reference_doc, fallback_title):
    task_description = data.get('task_description')
    if task_description:
        return task_description

    entities = (reference_doc or {}).get('entities', {})
    ref_title = (
        entities.get('perihal')
        or entities.get('subject')
        or (reference_doc or {}).get('filename')
        or fallback_title
        or 'Undangan'
    )

    date_str = data.get('date', _format_indonesian_date())
    time_str = data.get('time', '09:00 WIB')
    location_str = data.get('location', 'Kantor Pusat')
    return (
        f"Menghadiri dan berpartisipasi aktif dalam kegiatan '{ref_title}' "
        f"yang diselenggarakan pada tanggal {date_str} pukul {time_str} "
        f"berlokasi di {location_str}."
    )


def _build_generation_payload(data, current_user, requester, reference_doc=None):
    org_id = current_user.get('org_id')
    org = _find_org(org_id)
    org_name = org.get('name') if org else "Personal Workspace"

    delegation_id = (
        data.get('delegation_id')
        or requester.get('delegation_id')
        or current_user.get('delegation_id')
        or 'general'
    )
    delegation_name = _resolve_delegation_name(org_id, delegation_id)

    doc_number = data.get('doc_number') or data.get('letter_number') or ''
    date_str = data.get('date', _format_indonesian_date())
    time_str = data.get('time', '09:00 WIB')
    location_str = data.get('location', 'Kantor Pusat')
    city = data.get('city', 'Jakarta')
    signatory_name = data.get('signatory_name') or requester.get('username') or 'Kepala Instansi'

    task_description = _build_task_description(
        data,
        reference_doc,
        data.get('reference_title') or 'Undangan',
    )

    kop_name = data.get('kop') or ''
    ttd_name = data.get('ttd') or ''

    letterhead_asset = _get_asset(org_id, delegation_id, kop_name, ['kop', 'letterhead'])
    signature_asset = _get_asset(org_id, delegation_id, ttd_name, ['ttd', 'signature'])

    letterhead_value = letterhead_asset.get('image_data') if letterhead_asset else None
    signature_value = signature_asset.get('image_data') if signature_asset else None

    return {
        "doc_number": doc_number,
        "task_description": task_description,
        "signatory_name": signatory_name,
        "delegation_id": delegation_id,
        "delegation_name": delegation_name,
        "org_name": org_name,
        "reference_doc_id": data.get('reference_doc_id', ''),
        "reference_title": data.get('reference_title', ''),
        "date": date_str,
        "time": time_str,
        "location": location_str,
        "city": city,
        "kop": kop_name,
        "ttd": ttd_name,
        "letterhead_value": letterhead_value,
        "signature_value": signature_value,
        "current_date": _format_indonesian_date(),
    }


def _build_html_content(payload):
    return render_template_string(
        SURAT_TUGAS_TEMPLATE,
        doc_number=payload['doc_number'],
        task_description=payload['task_description'],
        signatory_name=payload['signatory_name'],
        delegation_name=payload['delegation_name'],
        org_name=payload['org_name'],
        letterhead=payload['letterhead_value'],
        signature=payload['signature_value'],
        city=payload['city'],
        current_date=payload['current_date'],
    )


def _build_doc_record(doc_id, payload, current_user, requester, status):
    classification = {"label": "LABEL_2", "label_name": "Surat Tugas"}
    entities = {
        "dates": [payload['date']] if payload['date'] else [],
        "nomor_surat": payload['doc_number'],
        "perihal": "Surat Tugas",
        "organisasi_penerbit": payload['org_name'],
    }

    sanitized_number = _sanitize_filename_component(payload['doc_number'])
    filename = f"SURAT_TUGAS_{sanitized_number}.pdf"

    return {
        "doc_id": doc_id,
        "filename": filename,
        "content": payload['task_description'],
        "summary": payload['task_description'],
        "status": status,
        "classification": classification,
        "entities": entities,
        "org_id": current_user.get('org_id'),
        "uploaded_by": current_user.get('user_id'),
        "uploaded_by_name": requester.get('username') or current_user.get('username'),
        "delegation_id": payload['delegation_id'],
        "mimetype": "application/pdf",
        "is_generated": True,
        "generator_type": "surat_tugas",
        "generator_status": status,
        "generated_data": {
            "doc_number": payload['doc_number'],
            "task_description": payload['task_description'],
            "signatory_name": payload['signatory_name'],
            "reference_doc_id": payload['reference_doc_id'],
            "reference_title": payload['reference_title'],
            "date": payload['date'],
            "time": payload['time'],
            "location": payload['location'],
            "city": payload['city'],
            "kop": payload['kop'],
            "ttd": payload['ttd'],
        },
        "html_content": _build_html_content(payload),
        "uploaded_at": datetime.datetime.utcnow().isoformat(),
        "created_at": datetime.datetime.utcnow(),
    }


def _upload_pdf_to_owner_drive(org_id, pdf_bytes, filename):
    owner = users_col.find_one({
        "org_id": org_id,
        "role": "owner",
        "google_drive_connected": True,
    })
    if not owner:
        raise Exception("Owner belum menghubungkan Google Drive organisasi.")

    refresh_token = owner.get("google_oauth", {}).get("refresh_token")
    if not refresh_token:
        raise Exception("Refresh token Google Drive owner tidak tersedia.")

    return upload_file_to_google_drive(
        io.BytesIO(pdf_bytes),
        filename,
        "application/pdf",
        refresh_token,
    )


def _finalize_generated_document(doc, approver):
    org_id = approver.get('org_id')
    generated_data = dict(doc.get('generated_data') or {})
    requester = _find_user(doc.get('uploaded_by')) or {
        "username": doc.get('uploaded_by_name') or 'Member',
        "delegation_id": doc.get('delegation_id') or 'general',
    }
    reference_doc = _find_reference_doc(generated_data.get('reference_doc_id'), org_id)

    payload = _build_generation_payload(
        generated_data,
        {
            "org_id": org_id,
            "delegation_id": doc.get('delegation_id') or approver.get('delegation_id'),
            "username": approver.get('username'),
        },
        requester,
        reference_doc=reference_doc,
    )

    if not payload['doc_number']:
        raise Exception("Nomor surat tugas belum tersedia pada request ini.")

    letterhead_image = _load_image_from_value(payload['letterhead_value'])
    signature_image = _load_image_from_value(payload['signature_value'])
    pdf_bytes = _render_assignment_pdf_bytes(payload, letterhead_image, signature_image)
    drive_data = _upload_pdf_to_owner_drive(org_id, pdf_bytes, doc['filename'])

    verification_hash = hashlib.sha256(
        f"{doc['doc_id']}{datetime.datetime.utcnow().timestamp()}".encode()
    ).hexdigest()[:16]

    update_data = {
        "content": payload['task_description'],
        "summary": payload['task_description'],
        "status": "processed",
        "generator_status": "processed",
        "google_drive": drive_data,
        "file_data": None,
        "verification_hash": verification_hash,
        "approved_by": approver.get('user_id'),
        "approved_by_name": approver.get('username'),
        "approved_at": datetime.datetime.utcnow(),
        "uploaded_at": datetime.datetime.utcnow().isoformat(),
        "html_content": _build_html_content(payload),
        "generated_data": {
            **generated_data,
            "signatory_name": payload['signatory_name'],
            "kop": payload['kop'],
            "ttd": payload['ttd'],
            "date": payload['date'],
            "time": payload['time'],
            "location": payload['location'],
            "city": payload['city'],
            "task_description": payload['task_description'],
        },
        "entities": {
            "dates": [payload['date']] if payload['date'] else [],
            "nomor_surat": payload['doc_number'],
            "perihal": "Surat Tugas",
            "organisasi_penerbit": payload['org_name'],
        },
        "classification": {"label": "LABEL_2", "label_name": "Surat Tugas"},
        "mimetype": "application/pdf",
    }

    docs_col.update_one({"doc_id": doc['doc_id'], "org_id": org_id}, {"$set": update_data})
    updated = docs_col.find_one({"doc_id": doc['doc_id'], "org_id": org_id})
    updated.pop("_id", None)
    return updated


@generator_bp.route('/surat-tugas', methods=['POST'])
@token_required
def generate_surat_tugas(current_user):
    inserted_doc_id = None
    try:
        user_id = current_user.get('user_id')
        org_id = current_user.get('org_id')
        role = current_user.get('role', 'member')
        requester = _find_user(user_id) or {"username": current_user.get('username'), "delegation_id": current_user.get('delegation_id')}

        data = request.get_json(force=True, silent=True) or {}
        reference_doc = _find_reference_doc(data.get('reference_doc_id'), org_id)
        payload = _build_generation_payload(data, current_user, requester, reference_doc=reference_doc)

        if not payload['doc_number'] or not payload['task_description']:
            return jsonify({"error": "Nomor surat dan isi surat tugas wajib tersedia."}), 400

        doc_id = uuid.uuid4().hex

        if role == 'owner':
            base_record = _build_doc_record(doc_id, payload, current_user, requester, 'processing')
            docs_col.insert_one(base_record)
            inserted_doc_id = doc_id
            finalized = _finalize_generated_document(base_record, current_user)

            log_event(
                "generator_service",
                f"Owner generated Surat Tugas PDF {doc_id}",
                user_id=user_id,
                org_id=org_id,
                action="GENERATE_SURAT_TUGAS_SUCCESS",
                metadata={"doc_id": doc_id, "filename": finalized.get("filename")},
                audience="owner",
                visibility="app",
                severity="info",
            )

            return jsonify({
                "message": "Surat tugas berhasil diterbitkan ke PDF dan diunggah ke Google Drive.",
                "doc_id": doc_id,
                "status": "processed",
                "html": finalized.get("html_content"),
                "google_drive": finalized.get("google_drive"),
                "verification_hash": finalized.get("verification_hash"),
            }), 201

        pending_record = _build_doc_record(doc_id, payload, current_user, requester, 'pending_approval')
        pending_record["requested_to_owner"] = True
        pending_record["request_created_at"] = datetime.datetime.utcnow()
        docs_col.insert_one(pending_record)

        log_event(
            "generator_service",
            f"Member submitted Surat Tugas request {doc_id}",
            user_id=user_id,
            org_id=org_id,
            action="SURAT_TUGAS_REQUEST_CREATED",
            metadata={"doc_id": doc_id, "filename": pending_record.get("filename")},
            audience="owner",
            visibility="app",
            severity="info",
        )

        return jsonify({
            "message": "Permintaan surat tugas berhasil dikirim ke owner untuk diterbitkan.",
            "doc_id": doc_id,
            "status": "pending_approval",
            "html": pending_record.get("html_content"),
        }), 201
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        if inserted_doc_id:
            docs_col.delete_one({
                "doc_id": inserted_doc_id,
                "org_id": current_user.get('org_id'),
                "status": "processing",
                "is_generated": True,
            })
        log_event(
            "generator_service",
            f"Error generating Surat Tugas: {str(e)}",
            user_id=current_user.get('user_id'),
            org_id=current_user.get('org_id'),
            action="GENERATE_SURAT_TUGAS_ERROR",
            metadata={"error": error_details},
        )
        return jsonify({
            "error": "Internal Server Error during Surat Tugas generation",
            "details": str(e),
        }), 500


@generator_bp.route('/surat-tugas/<doc_id>/approve', methods=['POST'])
@token_required
@role_required('owner')
def approve_surat_tugas(current_user, doc_id):
    org_id = current_user.get('org_id')
    doc = docs_col.find_one({
        "doc_id": doc_id,
        "org_id": org_id,
        "is_generated": True,
        "generator_type": "surat_tugas",
    })

    if not doc:
        return jsonify({"error": "Request surat tugas tidak ditemukan."}), 404

    if doc.get('generator_status') != 'pending_approval':
        return jsonify({"error": "Surat tugas ini tidak berada dalam status menunggu persetujuan."}), 400

    try:
        finalized = _finalize_generated_document(doc, current_user)
        log_event(
            "generator_service",
            f"Owner approved Surat Tugas request {doc_id}",
            user_id=current_user.get('user_id'),
            org_id=org_id,
            action="SURAT_TUGAS_REQUEST_APPROVED",
            metadata={"doc_id": doc_id, "filename": finalized.get("filename")},
            audience="owner",
            visibility="app",
            severity="info",
        )
        return jsonify({
            "message": "Surat tugas berhasil diterbitkan ke PDF dan diunggah ke Google Drive.",
            "doc_id": doc_id,
            "status": "processed",
            "google_drive": finalized.get("google_drive"),
            "verification_hash": finalized.get("verification_hash"),
        }), 200
    except Exception as e:
        log_event(
            "generator_service",
            f"Gagal approve Surat Tugas {doc_id}: {str(e)}",
            user_id=current_user.get('user_id'),
            org_id=org_id,
            action="SURAT_TUGAS_REQUEST_APPROVE_FAILED",
            metadata={"doc_id": doc_id, "error": str(e)},
        )
        return jsonify({"error": str(e)}), 500


@generator_bp.route('/verify/<doc_hash>', methods=['GET'])
def verify_document(doc_hash):
    doc = docs_col.find_one({"verification_hash": doc_hash})
    if not doc:
        return jsonify({"valid": False, "message": "Document hash not found. This might be a forgery."}), 404

    created_at = doc.get('created_at')
    created_at_value = created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)

    return jsonify({
        "valid": True,
        "message": "Document is AUTHENTIC",
        "details": {
            "doc_id": doc['doc_id'],
            "org_id": doc['org_id'],
            "created_at": created_at_value,
        }
    }), 200


@generator_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "generator_service"}), 200

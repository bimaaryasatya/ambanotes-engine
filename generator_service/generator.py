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
import qrcode
from bson import ObjectId
from PIL import Image, ImageDraw, ImageFont

# Add parent directory to path so we can import from common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, request, jsonify, render_template_string
from common.logger import log_event
from common.jwt_utils import token_required, role_required
from common.db import users_col, delegations_col, assets_col, docs_col, orgs_col
from common.google_drive_client import upload_file_to_google_drive
from common.config import Config

generator_bp = Blueprint('generator', __name__)

PUBLIC_VERIFY_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Verifikasi Dokumen</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f5f7fb; color: #172033; margin: 0; padding: 24px; }
        .card { max-width: 760px; margin: 40px auto; background: #fff; border-radius: 18px; box-shadow: 0 20px 50px rgba(18, 28, 45, 0.12); padding: 28px; }
        .badge { display: inline-block; padding: 8px 14px; border-radius: 999px; font-weight: 700; margin-bottom: 18px; }
        .ok { background: #e6f7ee; color: #146c43; }
        .bad { background: #fdecec; color: #b42318; }
        h1 { margin: 0 0 12px; font-size: 28px; }
        p { line-height: 1.6; }
        .meta { margin-top: 22px; border-top: 1px solid #e5e7eb; padding-top: 18px; }
        .meta-row { margin: 10px 0; }
        .label { font-weight: 700; }
        .hash { margin-top: 22px; font-family: Consolas, monospace; color: #475467; word-break: break-all; }
    </style>
</head>
<body>
    <div class="card">
        <div class="badge {{ 'ok' if valid else 'bad' }}">{{ 'VALID' if valid else 'TIDAK VALID' }}</div>
        <h1>{{ title }}</h1>
        <p>{{ message }}</p>
        {% if valid %}
        <div class="meta">
            <div class="meta-row"><span class="label">Jenis dokumen:</span> {{ details.doc_type }}</div>
            <div class="meta-row"><span class="label">Nomor surat:</span> {{ details.doc_number }}</div>
            <div class="meta-row"><span class="label">Organisasi:</span> {{ details.org_name }}</div>
            <div class="meta-row"><span class="label">Tanggal terbit:</span> {{ details.created_at }}</div>
            <div class="meta-row"><span class="label">Dokumen ID:</span> {{ details.doc_id }}</div>
        </div>
        {% endif %}
        <div class="hash">Verification ID: {{ doc_hash }}</div>
    </div>
</body>
</html>
"""


SURAT_TUGAS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: "Times New Roman", Times, serif; line-height: 1.65; margin: 36px; color: #111; }
        .kop-surat { text-align: center; border-bottom: 3px solid black; padding-bottom: 12px; margin-bottom: 24px; }
        .kop-img { max-width: 100%; height: auto; }
        .title { text-align: center; text-decoration: underline; font-weight: bold; font-size: 18px; margin-bottom: 5px; }
        .nomor { text-align: center; margin-bottom: 30px; }
        .content { margin-bottom: 20px; }
        .footer { margin-top: 50px; float: right; width: 300px; text-align: center; }
        .signature-img { max-width: 150px; margin: 10px 0; }
        .sign-location { margin: 8px 0 4px; font-size: 14px; }
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
        <p>Yang bertanda tangan di bawah ini:</p>
        <table class="details-table">
            <tr>
                <td style="width: 120px;">Nama</td>
                <td style="width: 15px;">:</td>
                <td><strong>{{ signatory_name }}</strong></td>
            </tr>
            <tr>
                <td>Jabatan</td>
                <td>:</td>
                <td>{{ signatory_jabatan }}</td>
            </tr>
        </table>

        <p style="margin-top: 16px;">Dengan ini menugaskan kepada:</p>
        <table class="details-table">
            <tr>
                <td style="width: 120px;">Nama</td>
                <td style="width: 15px;">:</td>
                <td><strong>{{ assignee_names }}</strong></td>
            </tr>
            <tr>
                <td>Jabatan</td>
                <td>:</td>
                <td>{{ assignee_jabatan }}</td>
            </tr>
        </table>

        <p style="margin-top: 24px;">Pada Pekerjaan/Kegiatan: <strong>{{ task_description }}</strong></p>
        
        <p style="margin-top: 20px;">Demikian surat tugas ini dibuat sebagaimana mestinya dan untuk dapat dipergunakan seperlunya.</p>
    </div>

    <div class="footer">
        <p>{{ city }}, {{ current_date }}</p>
        {% if current_location_label %}
            <p class="sign-location">{{ current_location_label }}</p>
        {% endif %}
        <p>Hormat Kami,</p>
        {% if signature %}
            <img src="{{ signature }}" class="signature-img">
        {% else %}
            <div style="height: 80px;"></div>
        {% endif %}
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


def _get_public_base_url():
    return (Config.PUBLIC_BASE_URL or Config.GATEWAY_URL or "http://localhost:5009").rstrip("/")


def _build_verification_hash(doc_id):
    seed = f"{doc_id}:{datetime.datetime.utcnow().timestamp()}:{uuid.uuid4().hex}"
    return hashlib.sha256(seed.encode()).hexdigest()[:24]


def _build_verification_url(doc_hash):
    return f"{_get_public_base_url()}/verify/{doc_hash}"


def _build_verification_qr(url):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


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
    verify_font = _get_font(16, bold=False)

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

    # 1. Yang bertanda tangan di bawah ini:
    intro = "Yang bertanda tangan di bawah ini:"
    cursor_y = _draw_wrapped_paragraph(draw, intro, body_font, margin_x, cursor_y, usable_width)
    cursor_y += 20

    # Signatory details
    # Nama
    draw.text((margin_x + 30, cursor_y), "Nama", font=body_font, fill=(0, 0, 0))
    draw.text((margin_x + 180, cursor_y), ":", font=body_font, fill=(0, 0, 0))
    cursor_y = _draw_wrapped_paragraph(draw, payload['signatory_name'], body_bold_font, margin_x + 210, cursor_y, usable_width - 210)
    cursor_y += 12

    # Jabatan
    draw.text((margin_x + 30, cursor_y), "Jabatan", font=body_font, fill=(0, 0, 0))
    draw.text((margin_x + 180, cursor_y), ":", font=body_font, fill=(0, 0, 0))
    cursor_y = _draw_wrapped_paragraph(draw, payload['signatory_jabatan'], body_font, margin_x + 210, cursor_y, usable_width - 210)
    cursor_y += 36

    # 2. Dengan ini menugaskan kepada:
    assign_intro = "Dengan ini menugaskan kepada:"
    cursor_y = _draw_wrapped_paragraph(draw, assign_intro, body_font, margin_x, cursor_y, usable_width)
    cursor_y += 20

    # Assignee details
    # Nama
    draw.text((margin_x + 30, cursor_y), "Nama", font=body_font, fill=(0, 0, 0))
    draw.text((margin_x + 180, cursor_y), ":", font=body_font, fill=(0, 0, 0))
    cursor_y = _draw_wrapped_paragraph(draw, payload['assignee_names'], body_bold_font, margin_x + 210, cursor_y, usable_width - 210)
    cursor_y += 12

    # Jabatan
    draw.text((margin_x + 30, cursor_y), "Jabatan", font=body_font, fill=(0, 0, 0))
    draw.text((margin_x + 180, cursor_y), ":", font=body_font, fill=(0, 0, 0))
    cursor_y = _draw_wrapped_paragraph(draw, payload['assignee_jabatan'], body_font, margin_x + 210, cursor_y, usable_width - 210)
    cursor_y += 36

    # 3. Pada Pekerjaan/Kegiatan:
    task_intro = f"Pada Pekerjaan/Kegiatan: {payload['task_description']}"
    cursor_y = _draw_wrapped_paragraph(draw, task_intro, body_font, margin_x, cursor_y, usable_width)
    cursor_y += 36

    # Reserve space for the verification footer so it never overlaps body content.
    verification_footer_height = 140
    footer_limit_y = page_height - verification_footer_height - 40

    # 4. Closing
    closing = "Demikian surat tugas ini dibuat sebagaimana mestinya dan untuk dapat dipergunakan seperlunya."
    cursor_y = _draw_wrapped_paragraph(draw, closing, body_font, margin_x, cursor_y, usable_width)
    cursor_y += 80

    if cursor_y > footer_limit_y:
        cursor_y = footer_limit_y

    footer_x = page_width - 420
    draw.text((footer_x, cursor_y), f"{payload['city']}, {payload['current_date']}", font=small_font, fill=(0, 0, 0))
    cursor_y += 42

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

    verification_hash = payload.get("verification_hash")
    verification_url = payload.get("verification_url")
    if verification_hash and verification_url:
        qr_image = _build_verification_qr(verification_url).resize((110, 110))
        verify_y = page_height - 126
        qr_x = page_width - margin_x - qr_image.width
        text_right_padding = 26
        text_max_width = qr_x - margin_x - text_right_padding

        draw.line((margin_x, verify_y - 14, page_width - margin_x, verify_y - 14), fill=(185, 185, 185), width=1)
        page.paste(qr_image, (qr_x, verify_y))

        draw.text(
            (margin_x, verify_y),
            f"Verification ID: {verification_hash}",
            font=verify_font,
            fill=(90, 90, 90),
        )
        url_lines = _wrap_text(draw, f"Verify: {verification_url}", verify_font, text_max_width)
        line_height = draw.textbbox((0, 0), "Ag", font=verify_font)[3] + 6
        url_y = verify_y + 24
        for line in url_lines[:3]:
            draw.text((margin_x, url_y), line, font=verify_font, fill=(90, 90, 90))
            url_y += line_height

        qr_label = "Scan to verify"
        qr_label_box = draw.textbbox((0, 0), qr_label, font=verify_font)
        qr_label_x = qr_x + (qr_image.width - (qr_label_box[2] - qr_label_box[0])) / 2
        draw.text((qr_label_x, verify_y + qr_image.height + 4), qr_label, font=verify_font, fill=(90, 90, 90))

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
        or (reference_doc.get('delegation_id') if reference_doc else None)
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

    # Fetch assignee members from the delegation (division)
    assigned_members = []
    if delegation_id and delegation_id != 'general':
        users_in_del = list(users_col.find({
            "org_id": org_id,
            "delegation_id": {"$in": [delegation_id, _safe_object_id(delegation_id)]}
        }))
        assigned_members = [u.get('username') for u in users_in_del if u.get('username')]
    
    if not assigned_members:
        assigned_members = [requester.get('username') or current_user.get('username') or 'Member']
    
    assignee_names = ", ".join(assigned_members)
    assignee_jabatan = f"{delegation_name} {org_name}" if delegation_name and delegation_name != 'General' else org_name

    # Determine signatory's jabatan
    signatory_user = users_col.find_one({"username": signatory_name, "org_id": org_id})
    if not signatory_user:
        signatory_user = users_col.find_one({"_id": _safe_object_id(current_user.get('user_id'))})
    
    if signatory_user:
        sig_role = signatory_user.get('role', 'member')
        if sig_role == 'owner':
            signatory_jabatan = f"Direktur {org_name}"
        else:
            sig_del_id = signatory_user.get('delegation_id')
            sig_del_name = _resolve_delegation_name(org_id, sig_del_id) if sig_del_id else None
            if sig_del_name and sig_del_name != 'General':
                signatory_jabatan = f"Kepala Divisi {sig_del_name} {org_name}"
            else:
                signatory_jabatan = f"Staf {org_name}"
    else:
        signatory_jabatan = "Kepala Instansi"

    return {
        "doc_number": doc_number,
        "task_description": task_description,
        "signatory_name": signatory_name,
        "signatory_jabatan": signatory_jabatan,
        "assignee_names": assignee_names,
        "assignee_jabatan": assignee_jabatan,
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
        signatory_jabatan=payload['signatory_jabatan'],
        assignee_names=payload['assignee_names'],
        assignee_jabatan=payload['assignee_jabatan'],
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
        "title": f"Surat Tugas {payload['doc_number']}".strip(),
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
            "signatory_jabatan": payload['signatory_jabatan'],
            "assignee_names": payload['assignee_names'],
            "assignee_jabatan": payload['assignee_jabatan'],
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


def get_verification_document(doc_hash):
    return docs_col.find_one({"verification_hash": doc_hash})


def build_verification_result(doc_hash):
    doc = get_verification_document(doc_hash)
    if not doc:
        return {
            "valid": False,
            "title": "Dokumen tidak terverifikasi",
            "message": "Verification ID tidak ditemukan. Dokumen ini bisa jadi bukan hasil terbitan resmi AmbaNotes.",
            "doc_hash": doc_hash,
            "details": None,
        }

    generated_data = doc.get("generated_data") or {}
    entities = doc.get("entities") or {}
    created_at = doc.get("approved_at") or doc.get("created_at")
    created_at_value = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
    org = _find_org(doc.get("org_id"))

    return {
        "valid": True,
        "title": "Dokumen asli dan terdaftar",
        "message": "Dokumen ini cocok dengan catatan verifikasi resmi di server AmbaNotes.",
        "doc_hash": doc_hash,
        "details": {
            "doc_id": doc.get("doc_id"),
            "doc_type": doc.get("generator_type", "document").replace("_", " ").title(),
            "doc_number": generated_data.get("doc_number") or entities.get("nomor_surat") or "-",
            "org_name": (org or {}).get("name", "Organisasi tidak diketahui"),
            "created_at": created_at_value,
        },
    }


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

    verification_hash = _build_verification_hash(doc['doc_id'])
    verification_url = _build_verification_url(verification_hash)
    payload["verification_hash"] = verification_hash
    payload["verification_url"] = verification_url

    letterhead_image = _load_image_from_value(payload['letterhead_value'])
    signature_image = _load_image_from_value(payload['signature_value'])
    pdf_bytes = _render_assignment_pdf_bytes(payload, letterhead_image, signature_image)
    drive_data = _upload_pdf_to_owner_drive(org_id, pdf_bytes, doc['filename'])

    update_data = {
        "content": payload['task_description'],
        "summary": payload['task_description'],
        "status": "processed",
        "generator_status": "processed",
        "google_drive": drive_data,
        "file_data": None,
        "verification_hash": verification_hash,
        "verification_url": verification_url,
        "approved_by": approver.get('user_id'),
        "approved_by_name": approver.get('username'),
        "approved_at": datetime.datetime.utcnow(),
        "uploaded_at": datetime.datetime.utcnow().isoformat(),
        "html_content": _build_html_content(payload),
        "generated_data": {
            **generated_data,
            "signatory_name": payload['signatory_name'],
            "signatory_jabatan": payload['signatory_jabatan'],
            "assignee_names": payload['assignee_names'],
            "assignee_jabatan": payload['assignee_jabatan'],
            "kop": payload['kop'],
            "ttd": payload['ttd'],
            "date": payload['date'],
            "time": payload['time'],
            "location": payload['location'],
            "city": payload['city'],
            "task_description": payload['task_description'],
            "verification_hash": verification_hash,
            "verification_url": verification_url,
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
                "verification_url": finalized.get("verification_url"),
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
            severity="error",
        )
        return jsonify({
            "error": "Internal Server Error during Surat Tugas generation"
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
            "verification_url": finalized.get("verification_url"),
        }), 200
    except Exception as e:
        log_event(
            "generator_service",
            f"Gagal approve Surat Tugas {doc_id}: {str(e)}",
            user_id=current_user.get('user_id'),
            org_id=org_id,
            action="SURAT_TUGAS_REQUEST_APPROVE_FAILED",
            metadata={"doc_id": doc_id, "error": str(e)},
            severity="error",
        )
        return jsonify({"error": "Failed to approve Surat Tugas request"}), 500


@generator_bp.route('/verify/<doc_hash>', methods=['GET'])
def verify_document(doc_hash):
    result = build_verification_result(doc_hash)
    status_code = 200 if result["valid"] else 404
    return jsonify(result), status_code


@generator_bp.route('/verify/<doc_hash>/page', methods=['GET'])
def verify_document_page(doc_hash):
    result = build_verification_result(doc_hash)
    status_code = 200 if result["valid"] else 404
    return render_template_string(PUBLIC_VERIFY_TEMPLATE, **result), status_code


@generator_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "generator_service"}), 200

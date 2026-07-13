import requests
import json
import datetime
from common.config import Config
from common.logger import log_event

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
GOOGLE_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"

def refresh_access_token(refresh_token):
    """
    Menukarkan refresh_token lama dengan access_token yang baru dan masa aktifnya.
    """
    payload = {
        "client_id": Config.GOOGLE_CLIENT_ID,
        "client_secret": Config.GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    
    try:
        response = requests.post(GOOGLE_TOKEN_URL, data=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            access_token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            expiry_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)
            
            return {
                "access_token": access_token,
                "token_expiry": expiry_time
            }
        else:
            log_event("google_drive_client", f"Gagal refresh token. HTTP {response.status_code}: {response.text}", action="TOKEN_REFRESH_FAILED")
    except Exception as e:
        log_event("google_drive_client", f"Error sewaktu refresh token: {str(e)}", action="TOKEN_REFRESH_ERROR")
        
    return None


def make_file_public_viewable(file_id, access_token):
    """
    Mengubah hak akses file di Google Drive agar siapa pun yang memiliki link dapat melihatnya (reader).
    Ini diperlukan agar file bisa di-embed di UI aplikasi Flutter/React.
    """
    url = f"{GOOGLE_DRIVE_FILES_URL}/{file_id}/permissions"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "role": "reader",
        "type": "anyone"
    }
    
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        return res.status_code == 200
    except Exception as e:
        log_event("google_drive_client", f"Gagal mengubah permission file {file_id}: {str(e)}", action="SET_PERMISSION_FAILED")
        return False


def get_file_links(file_id, access_token):
    """
    Mengambil tautan webViewLink dan webContentLink untuk preview dan download file.
    """
    url = f"{GOOGLE_DRIVE_FILES_URL}/{file_id}?fields=webViewLink,webContentLink"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        log_event("google_drive_client", f"Gagal mengambil tautan untuk file {file_id}: {str(e)}", action="GET_LINKS_FAILED")
        
    return {}

def download_file_from_google_drive(file_id, refresh_token):
    """
    Download file binary dari Google Drive menggunakan file_id dan refresh_token.
    """
    token_data = refresh_access_token(refresh_token)
    if not token_data:
        raise Exception("Gagal mengautentikasi ke Google API. Refresh token tidak valid.")

    access_token = token_data["access_token"]

    url = f"{GOOGLE_DRIVE_FILES_URL}/{file_id}?alt=media"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 200:
            return response.content

        log_event(
            "google_drive_client",
            f"Gagal download file Google Drive. HTTP {response.status_code}: {response.text}",
            action="DRIVE_DOWNLOAD_FAILED"
        )
        raise Exception(f"Google Drive download failed HTTP {response.status_code}")

    except Exception as e:
        log_event(
            "google_drive_client",
            f"Error download file Google Drive {file_id}: {str(e)}",
            action="DRIVE_DOWNLOAD_ERROR"
        )
        raise

def delete_file_from_google_drive(file_id, refresh_token):
    """
    Menghapus file dari Google Drive menggunakan file_id dan refresh_token.
    """
    token_data = refresh_access_token(refresh_token)
    if not token_data:
        raise Exception("Gagal mengautentikasi ke Google API. Refresh token tidak valid.")

    access_token = token_data["access_token"]

    url = f"{GOOGLE_DRIVE_FILES_URL}/{file_id}"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        response = requests.delete(url, headers=headers, timeout=30)

        if response.status_code in [200, 204]:
            return True

        log_event(
            "google_drive_client",
            f"Gagal hapus file Google Drive. HTTP {response.status_code}: {response.text}",
            action="DRIVE_DELETE_FAILED"
        )
        return False

    except Exception as e:
        log_event(
            "google_drive_client",
            f"Error hapus file Google Drive {file_id}: {str(e)}",
            action="DRIVE_DELETE_ERROR"
        )
        return False

def upload_file_to_google_drive(file_stream, filename, mimetype, refresh_token):
    """
    Mengunggah file biner ke Google Drive milik user secara multipart.
    Mengembalikan dict berisi file_id, web_view_link, dan web_content_link jika sukses.
    """
    import uuid
    # 1. Dapatkan access token baru dengan me-refresh refresh_token
    token_data = refresh_access_token(refresh_token)
    if not token_data:
        raise Exception("Gagal mengautentikasi ke Google API. Refresh token tidak valid.")
        
    access_token = token_data["access_token"]
    
    # 2. Siapkan data multipart secara manual agar berformat multipart/related
    metadata = {
        "name": filename,
        "description": "Surat diunggah melalui AmbaNotes AI Engine"
    }
    
    boundary = f"AmbaNotesBoundary{uuid.uuid4().hex}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": f"multipart/related; boundary={boundary}"
    }
    
    metadata_part = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
    )
    
    file_header = (
        f"--{boundary}\r\n"
        f"Content-Type: {mimetype}\r\n\r\n"
    )
    
    close_part = f"\r\n--{boundary}--\r\n"
    
    # Membaca byte berkas dari file_stream
    if hasattr(file_stream, "read"):
        file_bytes = file_stream.read()
    elif isinstance(file_stream, bytes):
        file_bytes = file_stream
    else:
        file_bytes = str(file_stream).encode("utf-8")
        
    body = metadata_part.encode("utf-8") + file_header.encode("utf-8") + file_bytes + close_part.encode("utf-8")
    
    try:
        # Kirim request ke Google Drive Upload API
        response = requests.post(GOOGLE_DRIVE_UPLOAD_URL, data=body, headers=headers, timeout=30)
        
        if response.status_code == 200:
            res_json = response.json()
            file_id = res_json.get("id")
            
            # 3. Buat file bisa dibaca publik
            make_file_public_viewable(file_id, access_token)
            
            # 4. Ambil webViewLink & webContentLink
            links = get_file_links(file_id, access_token)
            
            return {
                "file_id": file_id,
                "web_view_link": links.get("webViewLink"),
                "web_content_link": links.get("webContentLink"),
                "uploaded_at": datetime.datetime.utcnow().isoformat()
            }
        else:
            raise Exception(f"Google API mengembalikan HTTP {response.status_code}: {response.text}")
            
    except Exception as e:
        log_event("google_drive_client", f"Error saat mengunggah file {filename}: {str(e)}", action="DRIVE_UPLOAD_ERROR")
        raise e

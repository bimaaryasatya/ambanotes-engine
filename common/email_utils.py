import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from common.config import Config
from common.logger import log_event

def send_email(subject, recipient_email, body_html):
    """
    Sends an email using the SMTP configuration in Config.
    """
    if not Config.MAIL_USERNAME or not Config.MAIL_PASSWORD:
        log_event("email_utils", "SMTP credentials not configured", action="SMTP_CREDENTIALS_MISSING")
        return False, "SMTP credentials not configured"

    msg = MIMEMultipart()
    msg['From'] = Config.MAIL_DEFAULT_SENDER or Config.MAIL_USERNAME
    msg['To'] = recipient_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body_html, 'html'))

    try:
        server = smtplib.SMTP(Config.MAIL_SERVER, Config.MAIL_PORT)
        if Config.MAIL_USE_TLS:
            server.starttls()
        
        server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        log_event("email_utils", f"Email sent successfully to {recipient_email}")
        return True, "Email sent successfully"
    except Exception as e:
        log_event("email_utils", f"Failed to send email to {recipient_email}: {str(e)}", action="EMAIL_FAILED")
        return False, str(e)

def send_otp_email(recipient_email, otp_code):
    """
    Sends a stylized OTP email to the user.
    """
    subject = "AmbaNotes - Kode Verifikasi Reset Password"
    
    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
            <h2 style="color: #2c3e50; text-align: center;">Reset Password AmbaNotes</h2>
            <p>Halo,</p>
            <p>Kami menerima permintaan untuk mereset password akun AmbaNotes Anda. Gunakan kode OTP di bawah ini untuk melanjutkan:</p>
            <div style="text-align: center; margin: 30px 0;">
                <span style="font-size: 32px; font-weight: bold; letter-spacing: 5px; background: #f4f4f4; padding: 10px 20px; border-radius: 5px; color: #3498db;">
                    {otp_code}
                </span>
            </div>
            <p>Kode ini berlaku selama 10 menit. Jika Anda tidak merasa melakukan permintaan ini, silakan abaikan email ini.</p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #777; text-align: center;">
                &copy; 2026 AmbaNotes Team. All rights reserved.
            </p>
        </div>
    </body>
    </html>
    """
    
    return send_email(subject, recipient_email, body_html)


def send_delete_account_otp_email(recipient_email, otp_code):
    """
    Sends a stylized OTP email to the user for account deletion verification.
    """
    subject = "AmbaNotes - Kode Verifikasi Penghapusan Akun"
    
    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
            <h2 style="color: #c0392b; text-align: center;">Permintaan Penghapusan Akun AmbaNotes</h2>
            <p>Halo,</p>
            <p>Kami menerima permintaan untuk menghapus akun AmbaNotes Anda secara permanen. Gunakan kode verifikasi OTP di bawah ini untuk mengonfirmasi tindakan ini:</p>
            <div style="text-align: center; margin: 30px 0;">
                <span style="font-size: 32px; font-weight: bold; letter-spacing: 5px; background: #fdf2f2; padding: 10px 20px; border-radius: 5px; color: #c0392b; border: 1px solid #f5c6cb;">
                    {otp_code}
                </span>
            </div>
            <p><strong>PENTING:</strong> Tindakan ini bersifat permanen. Seluruh data Anda (dokumen fisik, riwayat disposisi, riwayat percakapan AmbaAI, dan keanggotaan organisasi) akan dihapus selamanya dari sistem dan tidak dapat dipulihkan.</p>
            <p>Kode verifikasi ini berlaku selama 10 menit. Jika Anda tidak mengajukan permintaan ini, mohon abaikan email ini.</p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #777; text-align: center;">
                &copy; 2026 AmbaNotes Team. All rights reserved.
            </p>
        </div>
    </body>
    </html>
    """
    
    return send_email(subject, recipient_email, body_html)


def send_invitation_email(recipient_email, org_name, inviter_name):
    """
    Sends a beautiful invitation email to join an organization on AmbaNotes.
    """
    subject = f"Undangan Bergabung ke Organisasi {org_name} di AmbaNotes"
    
    body_html = f"""
    <html>
    <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9f9f9; padding: 20px 0;">
        <div style="max-width: 600px; margin: 0 auto; padding: 30px; background-color: #ffffff; border: 1px solid #eef2f5; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
            <div style="text-align: center; margin-bottom: 24px;">
                <h2 style="color: #1e293b; margin: 0; font-size: 24px; font-weight: bold; letter-spacing: -0.5px;">Undangan Kolaborasi AmbaNotes</h2>
                <p style="color: #64748b; margin-top: 4px; font-size: 14px;">Secretariat & Document Management Dashboard</p>
            </div>
            <hr style="border: 0; border-top: 1px solid #f1f5f9; margin-bottom: 24px;">
            <p style="font-size: 16px; color: #334155; margin-bottom: 16px;">Halo,</p>
            <p style="font-size: 15px; color: #334155; line-height: 1.6; margin-bottom: 16px;">
                Anda telah diundang secara resmi oleh <strong>{inviter_name}</strong> untuk bergabung ke organisasi/instansi <strong>{org_name}</strong> di platform <strong>AmbaNotes AI</strong>.
            </p>
            <p style="font-size: 15px; color: #334155; line-height: 1.6; margin-bottom: 24px;">
                Dengan bergabung, Anda dapat berkolaborasi dalam arsip persuratan, menikmati deteksi entitas otomatis berbasis AI, serta menggunakan asisten super cerdas AmbaAI.
            </p>
            <div style="text-align: center; margin: 32px 0;">
                <a href="https://notes.bimazznxt.my.id/register?email={recipient_email}" 
                   style="background: linear-gradient(135deg, #4f46e5, #3b82f6); color: #ffffff; padding: 14px 28px; text-decoration: none; font-weight: bold; font-size: 15px; border-radius: 12px; display: inline-block; box-shadow: 0 4px 6px rgba(59, 130, 246, 0.25);">
                    Terima & Daftar Undangan
                </a>
            </div>
            <div style="background-color: #f8fafc; border-left: 4px solid #3b82f6; padding: 12px 16px; border-radius: 8px; margin-bottom: 24px;">
                <p style="font-size: 13px; color: #475569; margin: 0;">
                    <strong>Catatan:</strong> Undangan ini dikaitkan dengan email ini. Silakan mendaftar menggunakan email ini agar sistem secara otomatis menghubungkan Anda dengan instansi.
                </p>
            </div>
            <hr style="border: 0; border-top: 1px solid #f1f5f9; margin: 24px 0;">
            <p style="font-size: 11px; color: #94a3b8; text-align: center; margin: 0;">
                Email ini dikirim secara otomatis oleh AmbaNotes Engine.<br>
                &copy; 2026 AmbaNotes Team. All rights reserved.
            </p>
        </div>
    </body>
    </html>
    """
    
    return send_email(subject, recipient_email, body_html)

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
        log_event("email_utils", "SMTP credentials not configured", level="error")
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
        log_event("email_utils", f"Failed to send email to {recipient_email}: {str(e)}", level="error")
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

import random
import string
import smtplib
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import make_msgid, formatdate


class OTPManager:
    def __init__(self,
                 sender_email: str,
                 sender_password: str,
                 smtp_server: str,
                 smtp_port: int = 465):
        self.sender_email: str = sender_email
        self.sender_password: str = sender_password
        self.smtp_server: str = smtp_server
        self.smtp_port: int = smtp_port

    def generate_otp(self, length: int = 6) -> str:
        """Membuat OTP dengan panjang tertentu (default: 6 digit angka)."""
        return ''.join(random.choices(string.digits, k=length))

    def send_otp_email(self, recipient_email: str, otp: str) -> bool:
        """Mengirim email OTP ke alamat tujuan."""
        subjects: list[str] = [
            "Kode verifikasi EatRush Anda",
            "Gunakan kode berikut untuk login EatRush",
            "EatRush — Kode verifikasi akun",
            "Kode OTP untuk EatRush",
        ]
        subject: str = random.choice(subjects)

        plain_body: str = (
            f"Kode OTP Anda adalah: {otp}\n\n"
            "Kode ini hanya berlaku sebentar. Jangan bagikan kode ini kepada siapa pun."
        )

        html_body: str = f"""
<!doctype html>
<html lang="id">
  <head>
    <meta charset="utf-8"/>
    <style>
      body {{ font-family: Arial; background:#f8fafc; }}
      .otp {{ font-size: 34px; font-weight: bold; color: #ff7a00; }}
    </style>
  </head>
  <body>
    <h3>Kode OTP Anda</h3>
    <div class="otp">{otp}</div>
    <p>Jangan bagikan kode ini kepada siapa pun.</p>
  </body>
</html>
"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"EatRush Delivery <{self.sender_email}>"
        msg["To"] = recipient_email
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="eatrushdelivery.web.id")

        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, [recipient_email], msg.as_string())

            print("OTP email sent successfully!")
            return True

        except Exception as e:
            print("Error sending OTP:", e)
            return False

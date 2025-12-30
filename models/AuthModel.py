from datetime import datetime, timedelta
from typing import Dict, Any
from flask import redirect, url_for, session, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
from .db import get_db_connection
from mysql.connector import errors as mysql_errors
from .OTPManager import OTPManager
import requests
import os
from google_auth_oauthlib.flow import Flow
import secrets
import unicodedata

class AuthModel:
    _nama_pengguna: str
    _email: str
    _password: str
    _peran: str
    _identifier: str
    _otp_manager: OTPManager
    _otp: str
    _pending_user: Dict[str, Any]
    _reset_email: str
    _reset_otp: str

    def __init__(self, nama_pengguna: str, email: str, password: str, peran: str, identifier: str, is_login: bool = False) -> None:
        self._otp_manager = OTPManager(
            sender_email="delivery@eatrushdelivery.web.id",
            sender_password="6!6Sgk1KP5s+Md",
            smtp_server="mail.eatrushdelivery.web.id"
        )
        self._nama_pengguna = nama_pengguna
        self._email = email
        self._peran = peran
        self._identifier = identifier
        self._password = password if is_login else generate_password_hash(password)
        self._otp = self._otp_manager.generate_otp()
        self._pending_user = {
            'nama_pengguna': self._nama_pengguna,
            'email': self._email,
            'password': self._password,
            'peran': self._peran,
            'otp': self._otp,
            'otp_expiry': (datetime.now() + timedelta(minutes=5)).isoformat()
        }
        self._reset_email = ""
        self._reset_otp = ""

    def signup_user(self) -> Any:
        session['pending_user'] = self._pending_user
        self._otp_manager.send_otp_email(self._email, self._otp)
        return jsonify({'status': 'success', 'redirect': '/verify_otp'})

    
    def verify_otp(self, otp_input: str = "", resend: bool = False) -> Any:
        self._pending_user = session.get('pending_user')
        if not self._pending_user:
            return jsonify({'status': 'fail', 'message': 'Tidak ada sesi pendaftaran aktif.'})
        if resend:
            self._otp = self._otp_manager.generate_otp()
            self._pending_user['otp'] = self._otp
            self._pending_user['otp_expiry'] = (datetime.now() + timedelta(minutes=5)).isoformat()
            session['pending_user'] = self._pending_user
            self._otp_manager.send_otp_email(self._pending_user['email'], self._otp)
            return jsonify({'status': 'ok', 'message': 'OTP baru dikirim (berlaku 5 menit).'})
    
        if not otp_input:
            return jsonify({'status': 'fail', 'message': 'OTP tidak boleh kosong.'})
    
        otp_expiry = datetime.fromisoformat(self._pending_user['otp_expiry'])
        if datetime.now() > otp_expiry:
            session.pop('pending_user', None)
            return jsonify({'status': 'fail', 'message': 'OTP sudah kedaluwarsa. Silakan kirim ulang.'})
    
        if otp_input != self._pending_user['otp']:
            return jsonify({'status': 'fail', 'message': 'OTP salah!'})
    
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT * FROM Pengguna WHERE Email=%s", (self._pending_user['email'],))
            existing = cur.fetchone()
            if existing:
                session.pop('pending_user', None)
                session['user'] = {
                    'IdPengguna': existing['IdPengguna'], # atau user['IdPengguna']
                    'NamaPengguna': existing['NamaPengguna'],
                    'Email': existing['Email'],
                    'Peran': existing['Peran'],
                    'nomorTeleponPengguna': existing.get('nomorTeleponPengguna')
                }
                return jsonify({'status': 'success', 'message': 'Email sudah terdaftar. Login otomatis.'})
    
            try:
                cur2 = conn.cursor()
                cur2.execute(
                    "INSERT INTO Pengguna (NamaPengguna, Email, Password, Peran) VALUES (%s, %s, %s, %s)",
                    (
                        self._pending_user['nama_pengguna'],
                        self._pending_user['email'],
                        self._pending_user['password'],
                        self._pending_user['peran']
                    )
                )
                conn.commit()
                cur2.close()
    
                cur.execute("SELECT * FROM Pengguna WHERE Email=%s", (self._pending_user['email'],))
                user = cur.fetchone()
                session.pop('pending_user', None)
                session['user'] = user
                return jsonify({'status': 'success', 'message': 'Registrasi berhasil!'})
            except mysql_errors.IntegrityError as ie:
                conn.rollback()
                cur.execute("SELECT * FROM Pengguna WHERE Email=%s", (self._pending_user['email'],))
                user = cur.fetchone()
                session.pop('pending_user', None)
                if user:
                    session['user'] = user
                    return jsonify({'status': 'success', 'message': 'Email sudah ada, login otomatis.'})
                return jsonify({'status': 'fail', 'message': 'Gagal menyimpan pengguna (duplikat).'}), 409
            except Exception as e:
                conn.rollback()
                return jsonify({'status': 'fail', 'message': f'Error saat menyimpan pengguna: {str(e)}'}), 500
        finally:
            cur.close()
            conn.close()

    def _normalize_string(self, s: str) -> str:
        if s is None:
            return s
        s = unicodedata.normalize("NFKC", s)
        s = s.replace('\u00A0', ' ')
        s = ' '.join(s.split())
        return s.strip()
    
    def login_user(self, identifier: str, password: str) -> any:
        self._identifier = identifier
        norm_identifier = self._normalize_string(identifier)
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        user = None
        try:
            cur.execute("SELECT * FROM Pengguna WHERE Email=%s", (identifier,))
            user = cur.fetchone()
            if not user and norm_identifier:
                cur.execute(
                    "SELECT * FROM Pengguna WHERE LOWER(TRIM(NamaPengguna)) = LOWER(TRIM(%s))",
                    (norm_identifier,)
                )
                user = cur.fetchone()
        finally:
            cur.close()
            conn.close()
        if user:
            try:
                ok = check_password_hash(user['Password'], password)
            except Exception:
                ok = False
            if ok:
                return user
        return None

    def send_reset_otp(self, email: str) -> Any:
        self._reset_email = email
        self._reset_otp = self._otp_manager.generate_otp()
        session['reset_email'] = self._reset_email
        session['reset_otp'] = self._reset_otp
        self._otp_manager.send_otp_email(email, self._reset_otp)
        return jsonify({'status': 'ok', 'message': 'OTP reset dikirim ke email'})

    def reset_password(self, otp_input: str, new_password: str) -> Any:
        if otp_input != session.get('reset_otp'):
            return jsonify({'status': 'fail', 'message': 'OTP salah!'})
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE Pengguna SET Password=%s WHERE Email=%s",
            (generate_password_hash(new_password), session['reset_email'])
        )
        conn.commit()
        cur.close()
        conn.close()
        session.pop('reset_email', None)
        session.pop('reset_otp', None)
        return jsonify({'status': 'success', 'message': 'Password berhasil diubah'})

    def login_google(self) -> Any:
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        GOOGLE_CLIENT_ID = "115327895675-kcg53osh0ff52h38bde5qeeoo15gfsel.apps.googleusercontent.com"
        GOOGLE_CLIENT_SECRET = "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"
        REDIRECT_URI = "https://eatrushdelivery.web.id/callback"
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [REDIRECT_URI],
                }
            },
            scopes=["https://www.googleapis.com/auth/userinfo.email", "openid"]
        )
        flow.redirect_uri = REDIRECT_URI
        authorization_url, _ = flow.authorization_url(prompt='consent')
        return redirect(authorization_url)

    def google_callback(self) -> Any:
        try:
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
            GOOGLE_CLIENT_ID = "115327895675-kcg53osh0ff52h38bde5qeeoo15gfsel.apps.googleusercontent.com"
            GOOGLE_CLIENT_SECRET = "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"
            REDIRECT_URI = "https://eatrushdelivery.web.id/callback"
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": GOOGLE_CLIENT_ID,
                        "client_secret": GOOGLE_CLIENT_SECRET,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                scopes=["https://www.googleapis.com/auth/userinfo.email", "openid"],
                redirect_uri=REDIRECT_URI
            )
            authorization_response = request.url
            if authorization_response.startswith('http:'):
                authorization_response = authorization_response.replace('http:', 'https:', 1)
            
            flow.fetch_token(authorization_response=authorization_response)
            
            # Ambil info user dari Google
            credentials = flow.credentials
            r = requests.get('https://www.googleapis.com/oauth2/v2/userinfo', headers={'Authorization': f'Bearer {credentials.token}'})
            info = r.json()

        except Exception as e:
            # Error handling logging
            import traceback
            tb = traceback.format_exc()
            try:
                current_app.logger.error("GOOGLE CALLBACK ERROR: %s\n%s", e, tb)
            except Exception:
                print("GOOGLE CALLBACK ERROR:", e)
            return jsonify({'status': 'error', 'message': 'Google callback gagal', 'detail': str(e)}), 500


        self._email = info.get('email')

        if self._email:
            if '@' in self._email:
                self._nama_pengguna = self._email.split('@')[0]
            else:
                self._nama_pengguna = self._email
        else:
            self._nama_pengguna = "Pengguna"

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)

        data_db = None 
        
        try:
            
            cur.execute("SELECT * FROM Pengguna WHERE Email=%s", (self._email,))
            existing_user = cur.fetchone()

            if not existing_user:
                # User Baru: Insert
                raw_password = secrets.token_urlsafe(12)
                hashed = generate_password_hash(raw_password)
                
                cur.execute(
                    "INSERT INTO Pengguna (NamaPengguna, Email, Password, Peran) VALUES (%s, %s, %s, %s)",
                    (self._nama_pengguna, self._email, hashed, "pembeli")
                )
                conn.commit()
            
            else:
                
                if not existing_user.get('Password'):
                    raw_password = secrets.token_urlsafe(12)
                    hashed = generate_password_hash(raw_password)
                    cur.execute(
                        "UPDATE Pengguna SET Password=%s WHERE Email=%s",
                        (hashed, self._email)
                    )
                    conn.commit()

            # 2. Ambil Data Terbaru untuk Session
            cur.execute("SELECT * FROM Pengguna WHERE Email=%s", (self._email,))
            data_db = cur.fetchone()

        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

        # 3. Set Session & Redirect
        if data_db:
            session['user'] = {
                'IdPengguna': data_db.get('IdPengguna'),
                'NamaPengguna': data_db.get('NamaPengguna'),
                'Email': data_db.get('Email'),
                'Peran': data_db.get('Peran'), 
                'nomorTeleponPengguna': data_db.get('nomorTeleponPengguna')
            }

            if data_db.get('Peran') == 'penjual':
                return redirect(url_for('warung.home_warung'))
            else:
                return redirect(url_for('home.home'))

        # Fallback jika gagal
        return redirect(url_for('auth.auth_page'))

    def logout(self) -> Any:
        session.clear()
        return redirect(url_for('index'))

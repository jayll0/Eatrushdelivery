from flask import Blueprint, render_template, redirect, url_for, session, jsonify, request
from models.AuthModel import AuthModel

auth_bp = Blueprint("auth", __name__)

def _make_auth(nama_pengguna: str = "", email: str = "", password: str = "", peran: str = "", identifier: str = "", is_login: bool = False) -> AuthModel:
    return AuthModel(
        nama_pengguna=nama_pengguna,
        email=email,
        password=password,
        peran=peran,
        identifier=identifier,
        is_login=is_login
    )

@auth_bp.route("/auth", methods=["GET"])
def auth_page():
    return render_template("auth.html")

@auth_bp.route("/login", methods=["POST"])
def login():
    identifier = request.form.get("identifier", "").strip()
    password = request.form.get("password", "")
    if not identifier or not password:
        return jsonify({"status": "fail", "message": "Identifier dan password wajib."}), 400

    auth = _make_auth(
        nama_pengguna=identifier,
        email=identifier,
        password=password,
        peran="None",
        identifier=identifier,
        is_login=True
    )

    user = auth.login_user(identifier, password)
    if user:
        session["user"] = user
        return jsonify({"status": "success", "message": "Login berhasil"})
    return jsonify({"status": "fail", "message": "Email/Nama atau password salah"}), 401

@auth_bp.route("/register", methods=["POST"])
def register():
    nama_pengguna = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    peran = request.form.get("peran", "pembeli")
    if not nama_pengguna or not email or not password:
        return jsonify({"status": "fail", "message": "Nama, email, dan password wajib."}), 400

    auth = _make_auth(
        nama_pengguna=nama_pengguna,
        email=email,
        password=password,
        peran=peran,
        identifier=email,
        is_login=False
    )
    return auth.signup_user()

@auth_bp.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "GET":
        return render_template("verify_otp.html")

    pending = session.get("pending_user")
    if not pending:
        return jsonify({"status": "fail", "message": "Tidak ada sesi pendaftaran aktif."}), 400

    auth = _make_auth(
        nama_pengguna=pending.get("nama_pengguna", ""),
        email=pending.get("email", ""),
        password=pending.get("password", ""),
        peran=pending.get("peran"), 
        identifier=pending.get("email", ""),
        is_login=False
    )

    if "resend" in request.form:
        return auth.verify_otp("", resend=True)

    otp_value = request.form.get("otp", "")
    return auth.verify_otp(otp_value)

@auth_bp.route("/forgot", methods=["GET"])
def forgot_page():
    return render_template("forgot.html")

@auth_bp.route("/forgot", methods=["POST"])
def forgot():
    email = request.form.get("email", "").strip()
    if not email:
        return jsonify({"status": "fail", "message": "Email wajib."}), 400

    auth = _make_auth(
        nama_pengguna=email,
        email=email,
        password="",
        peran="",
        identifier=email,
        is_login=True
    )
    return auth.send_reset_otp(email)

@auth_bp.route("/reset_password", methods=["POST"])
def reset_password():
    otp = request.form.get("otp", "")
    new_password = request.form.get("new_password", "")
    if not otp or not new_password:
        return jsonify({"status": "fail", "message": "OTP dan password baru wajib."}), 400

    reset_email = session.get("reset_email", "") or ""
    auth = _make_auth(
        nama_pengguna=reset_email,
        email=reset_email,
        password="",
        peran="",
        identifier=reset_email,
        is_login=True
    )
    return auth.reset_password(otp, new_password)

@auth_bp.route("/login_google")
def login_google():
    auth = _make_auth(
        nama_pengguna="",
        email="",
        password="",
        peran="",
        identifier="",
        is_login=True
    )
    return auth.login_google()

@auth_bp.route("/callback")
def callback():
    auth = _make_auth(
        nama_pengguna="",
        email="",
        password="",
        peran="",
        identifier="",
        is_login=True
    )
    return auth.google_callback()

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.auth_page"))

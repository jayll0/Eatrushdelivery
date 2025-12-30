# routes/pembayaran_routes.py
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    current_app,
)
from typing import Optional
from models.Pesanan import Pesanan, get_pesanan_detail
from datetime import datetime

pembayaran_bp = Blueprint("pembayaran", __name__, url_prefix="/pembayaran")


def _is_logged_in() -> bool:
    return "user" in session and session.get("user") is not None


def _get_session_user_id() -> Optional[int]:
    u = session.get("user") or {}
    try:
        return int(u.get("IdPengguna") or u.get("IdUser") or u.get("id"))
    except Exception:
        return None


@pembayaran_bp.route("/<int:id_pesanan>", methods=["GET"])
def pembayaran_page(id_pesanan: int):
    if not _is_logged_in():
        return redirect(url_for("auth.auth_page"))

    data = get_pesanan_detail(id_pesanan)
    if not data:
        current_app.logger.warning("Pembayaran: pesanan %s tidak ditemukan", id_pesanan)
        return "Pesanan tidak ditemukan", 404

    user = session.get("user", {})
    id_pembeli = _get_session_user_id()
    pw = data.get("pesanan") or {}
    # permission check: only buyer may open payment page
    try:
        pesanan_pembeli = pw.get("IdPembeli")
        if pesanan_pembeli is not None and id_pembeli is not None and int(pesanan_pembeli) != int(id_pembeli):
            return "Tidak punya akses ke halaman pembayaran ini", 403
    except Exception:
        # in doubt, block access
        return "Tidak punya akses ke halaman pembayaran ini", 403

    total = pw.get("TotalHarga") or 0
    # available payment methods — extend as needed
    payment_methods = current_app.config.get("PAYMENT_METHODS", ["Cash", "Transfer", "QRIS"])
    return render_template(
        "pembayaran.html",
        pesanan=pw,
        details=data.get("details", []),
        total=total,
        id_pesanan=id_pesanan,
        user=user,
        payment_methods=payment_methods,
    )


@pembayaran_bp.route("/<int:id_pesanan>", methods=["POST"])
def pembayaran_process(id_pesanan: int):
    is_ajax = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not _is_logged_in():
        if is_ajax:
            return jsonify({"success": False, "message": "Belum login"}), 401
        return redirect(url_for("auth.auth_page"))

    data = get_pesanan_detail(id_pesanan)
    if not data:
        if is_ajax:
            return jsonify({"success": False, "message": "Pesanan tidak ditemukan"}), 404
        return "Pesanan tidak ditemukan", 404

    user_id = _get_session_user_id()
    pw = data.get("pesanan") or {}
    try:
        pesanan_pembeli = pw.get("IdPembeli")
        if pesanan_pembeli is not None and user_id is not None and int(pesanan_pembeli) != int(user_id):
            if is_ajax:
                return jsonify({"success": False, "message": "Akses ditolak"}), 403
            return "Akses ditolak", 403
    except Exception:
        if is_ajax:
            return jsonify({"success": False, "message": "Akses ditolak"}), 403
        return "Akses ditolak", 403

    # allowed statuses before payment — default sesuai permintaan: hanya "Pembayaran"
    ALLOWED_BEFORE_PAY = set(current_app.config.get("ALLOWED_STATUS_BEFORE_PAYMENT", ["Pembayaran"]))
    current_status = str(pw.get("Status") or "")
    if current_status not in ALLOWED_BEFORE_PAY:
        msg = f"Pesanan tidak dapat dibayar saat status saat ini adalah '{current_status}'. Harus berstatus salah satu: {', '.join(ALLOWED_BEFORE_PAY)}."
        if is_ajax:
            return jsonify({"success": False, "message": msg}), 400
        flash(msg, "error")
        return redirect(url_for("pembayaran.pembayaran_page", id_pesanan=id_pesanan))

    # ambil metode pembayaran (AJAX JSON atau form)
    method = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        method = payload.get("metode") or payload.get("method") or payload.get("payment_method") or "Cash"
    else:
        method = request.form.get("metode") or request.form.get("method") or request.form.get("payment_method") or "Cash"
    method = method or "Cash"

    try:
        p = Pesanan(id_pesanan=id_pesanan)
        affected = p.mark_paid(payment_method=method)
        if not affected:
            # if mark_paid did not update rows, consider it an error
            raise RuntimeError("Status pembayaran gagal diupdate (0 rows affected)")
    except Exception as e:
        current_app.logger.exception("Gagal mark_paid pesanan %s: %s", id_pesanan, e)
        if is_ajax:
            return jsonify({"success": False, "message": "Gagal memproses pembayaran: " + str(e)}), 500
        flash("Gagal memproses pembayaran: " + str(e), "error")
        return redirect(url_for("pembayaran.pembayaran_page", id_pesanan=id_pesanan))

    success_redirect = url_for("pembayaran.pembayaran_selesai", id_pesanan=id_pesanan)
    if is_ajax:
        return jsonify({"success": True, "redirect": success_redirect, "id_pesanan": id_pesanan}), 200

    flash("Pembayaran berhasil dicatat. Pesanan berstatus 'Menunggu'.", "success")
    return redirect(success_redirect)


@pembayaran_bp.route("/selesai")
def pembayaran_selesai_index():
    return render_template("pembayaranSelesai.html")


@pembayaran_bp.route("/selesai/<int:id_pesanan>")
def pembayaran_selesai(id_pesanan: int):
    pesan = f"Pesanan #{id_pesanan} telah terkonfirmasi dan berstatus 'Menunggu'."
    return render_template("pembayaranSelesai.html", id_pesanan=id_pesanan, pesan=pesan)

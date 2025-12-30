# routes/keranjang_routes.py
from flask import (
    Blueprint,
    request,
    session,
    jsonify,
    current_app,
    render_template,
    redirect,
    url_for,
    flash,
)
from typing import List, Dict, Any, Optional
import re

from models.Keranjang import (
    add_item_to_server_cart,
    update_qty_in_server_cart,
    remove_item_from_server_cart,
)
from models.Makanan import Makanan
from models.Pesanan import Pesanan, delete_user_carts
from models.Obrolan import Obrolan

keranjang_bp = Blueprint("keranjang", __name__, url_prefix="/keranjang")

def _get_session_user_id() -> Optional[int]:
    u = session.get("user") or {}
    try:
        return int(u.get("IdPengguna") or u.get("IdUser") or u.get("id"))
    except Exception:
        return None

@keranjang_bp.route("/", methods=["GET"])
def keranjang_index():
    wid = request.args.get("warung")
    try:
        warung_id = int(wid) if wid is not None else None
    except Exception:
        warung_id = None
    user = session.get("user")
    return render_template("keranjang.html", warung_id=warung_id or 0, user=user)

@keranjang_bp.route("/<int:warung_id>", methods=["GET"])
def keranjang_view(warung_id: int):
    user = session.get("user")
    return render_template("keranjang.html", warung_id=warung_id, user=user)

@keranjang_bp.route("/get", methods=["GET"])
def get_server_cart():
    if "user" not in session:
        return jsonify({"success": False, "message": "Belum login"}), 401

    try:
        wid = request.args.get("warung")
        all_cart = session.get("server_cart") or {}
        if not isinstance(all_cart, dict):
            all_cart = {}

        if wid:
            cur = all_cart.get(str(wid), [])
            return jsonify({"success": True, "cart": cur}), 200
        return jsonify({"success": True, "cart": all_cart}), 200
    except Exception as e:
        current_app.logger.exception("Gagal ambil server cart: %s", e)
        return jsonify({"success": False, "message": "Gagal ambil keranjang"}), 500

@keranjang_bp.route("/tambah", methods=["POST"])
def tambah_keranjang():
    if "user" not in session:
        return jsonify({"success": False, "message": "Belum login"}), 401

    id_pembeli = _get_session_user_id()
    if not id_pembeli:
        return jsonify({"success": False, "message": "User tidak dikenali"}), 401

    payload = request.get_json(silent=True) or request.form or {}
    try:
        # Note sudah dihandle otomatis di dalam add_item_to_server_cart -> normalize_item
        ok, msg = add_item_to_server_cart(payload, user_id=int(id_pembeli))
        status = 200 if ok else 400

        switched_from = None
        try:
            # Cek apakah msg mengandung info switch warung (tergantung implementasi model)
            # Jika logic switch warung di model mengembalikan string khusus, parsing di sini
            if "warung" in str(msg).lower() and "dihapus" in str(msg).lower():
                 m = re.search(r"warung\s+(\d+)", str(msg))
                 if m: switched_from = int(m.group(1))
        except Exception:
            switched_from = None

        resp = {"success": ok, "message": msg, "cart": session.get("server_cart")}
        if switched_from is not None:
            resp["switched_from_warung"] = switched_from

        return jsonify(resp), status
    except Exception as e:
        current_app.logger.exception("Gagal tambah item: %s", e)
        return jsonify({"success": False, "message": "Gagal menambahkan item"}), 500

@keranjang_bp.route("/merge", methods=["POST"])
def merge_cart():
    if "user" not in session:
        return jsonify({"success": False, "message": "Belum login"}), 401

    id_pembeli = _get_session_user_id()
    if not id_pembeli:
        return jsonify({"success": False, "message": "User tidak dikenali"}), 401

    data = request.get_json(silent=True) or {}
    local_cart = data.get("cart") or []
    if not isinstance(local_cart, list):
        return jsonify({"success": False, "message": "Format cart salah"}), 400

    partial_failed: List[Dict[str, Any]] = []
    for raw in local_cart:
        try:
            ok, msg = add_item_to_server_cart(raw, user_id=int(id_pembeli))
            if not ok:
                partial_failed.append({"item": raw, "reason": msg})
        except Exception as e:
            current_app.logger.exception("Gagal merge item: %s", e)
            partial_failed.append({"item": raw, "reason": "exception"})

    status = 200 if not partial_failed else 207
    success = len(partial_failed) == 0
    return jsonify({"success": success, "cart": session.get("server_cart"), "partial_failed": partial_failed}), status

@keranjang_bp.route("/update_qty", methods=["POST"])
def api_update_qty():
    if "user" not in session:
        return jsonify({"success": False, "message": "Belum login"}), 401

    id_pembeli = _get_session_user_id()
    if not id_pembeli:
        return jsonify({"success": False, "message": "User tidak dikenali"}), 401

    data = request.get_json(silent=True) or request.form or {}
    try:
        warung_id = int(data.get("warung_id"))
        id_makanan = int(data.get("id_makanan"))
        qty = int(data.get("qty"))
        # REVISI: Ambil note agar bisa membedakan item
        note = str(data.get("note", "") or "").strip()
    except Exception:
        return jsonify({"success": False, "message": "Payload tidak valid"}), 400

    try:
        ok, msg = update_qty_in_server_cart(
            warung_id=warung_id, 
            id_makanan=id_makanan, 
            qty=qty, 
            user_id=int(id_pembeli),
            note=note  # Pass note ke model
        )
        status = 200 if ok else 400
        return jsonify({"success": ok, "message": msg, "cart": session.get("server_cart")}), status
    except Exception as e:
        current_app.logger.exception("Gagal update qty: %s", e)
        return jsonify({"success": False, "message": "Gagal update qty"}), 500

@keranjang_bp.route("/remove", methods=["POST"])
def api_remove_item():
    if "user" not in session:
        return jsonify({"success": False, "message": "Belum login"}), 401

    id_pembeli = _get_session_user_id()
    if not id_pembeli:
        return jsonify({"success": False, "message": "User tidak dikenali"}), 401

    data = request.get_json(silent=True) or request.form or {}
    try:
        warung_id = int(data.get("warung_id"))
        id_makanan = int(data.get("id_makanan"))
        # REVISI: Ambil note agar bisa menghapus item spesifik
        note = str(data.get("note", "") or "").strip()
    except Exception:
        return jsonify({"success": False, "message": "Payload tidak valid"}), 400

    try:
        ok, msg = remove_item_from_server_cart(
            warung_id=warung_id, 
            id_makanan=id_makanan, 
            user_id=int(id_pembeli),
            note=note # Pass note ke model
        )
        status = 200 if ok else 400
        return jsonify({"success": ok, "message": msg, "cart": session.get("server_cart")}), status
    except Exception as e:
        current_app.logger.exception("Gagal remove item: %s", e)
        return jsonify({"success": False, "message": "Gagal hapus item"}), 500

@keranjang_bp.route("/checkout", methods=["POST"])
def checkout():
    is_ajax = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if "user" not in session:
        if is_ajax:
            return jsonify({"success": False, "message": "Belum login"}), 401
        return redirect(url_for("auth.auth_page"))

    id_pembeli = _get_session_user_id()
    if not id_pembeli:
        if is_ajax:
            return jsonify({"success": False, "message": "User tidak dikenali"}), 401
        return redirect(url_for("auth.auth_page"))

    form = request.form or {}
    try:
        warung_id = int(form.get("warung") or request.args.get("warung") or 0)
    except Exception:
        warung_id = 0

    items = []

    server_cart = session.get("server_cart") or {}
    if isinstance(server_cart, dict) and warung_id and str(warung_id) in server_cart and server_cart[str(warung_id)]:
        for it in server_cart.get(str(warung_id), []):
            try:
                items.append({
                    "id_makanan": int(it.get("id_makanan") or it.get("id") or 0),
                    "qty": max(1, int(it.get("qty") or 1)),
                    "note": str(it.get("note") or "") 
                })
            except Exception:
                continue
    else:
        try:
            count = int(form.get("count") or 0)
        except Exception:
            count = 0
        for i in range(count):
            try:
                mid = int(form.get(f"id_{i}") or 0)
                qty = max(1, int(form.get(f"qty_{i}") or 1))
                note = form.get(f"note_{i}") or ""
                if mid > 0:
                    items.append({"id_makanan": mid, "qty": qty, "note": note})
            except Exception:
                continue

    if not items:
        if is_ajax:
            return jsonify({"success": False, "message": "Tidak ada item untuk dipesan"}), 400
        flash("Keranjang kosong.", "error")
        return redirect(url_for("keranjang.keranjang_index"))

    if not warung_id:
        try:
            first_mid = int(items[0]["id_makanan"])
            m = Makanan().get_by_id(first_mid)
            warung_id = int(m.get_id_warung())
        except Exception:
            warung_id = 0

    try:
        delete_user_carts(user_id=int(id_pembeli))
    except Exception:
        current_app.logger.exception("Gagal cleanup pesanan Pembayaran lama")

    try:
        p = Pesanan()
        id_pesanan = p.create_with_items(items=items, id_pembeli=int(id_pembeli), id_warung=int(warung_id), catatan=form.get("catatan") or "")

        # --- LOGIKA TAMBAHAN: TRIGGER CHAT ---
        try:
            id_ruang = Obrolan.get_or_create_room(int(id_pembeli), int(warung_id))
            pesan = Obrolan(
                id_pengguna=int(id_pembeli),
                id_warung=int(warung_id),
                id_ruang=id_ruang,
                pengirim='pembeli',
                isi="Halo, saya baru saja membuat pesanan baru.",
                reply_to_pesanan=id_pesanan
            )
            pesan.kirim()
        except Exception:
            pass
        # -------------------------------------

    except Exception as e:
        current_app.logger.exception("Checkout gagal: %s", e)
        if is_ajax:
            return jsonify({"success": False, "message": str(e)}), 400
        flash("Gagal membuat pesanan: " + str(e), "error")
        return redirect(url_for("keranjang.keranjang_index"))

    try:
        all_cart = session.get("server_cart") or {}
        if isinstance(all_cart, dict):
            all_cart.pop(str(warung_id), None)
            session['server_cart'] = all_cart
            session.modified = True
    except Exception:
        current_app.logger.exception("Gagal clear server_cart session")

    target_url = url_for("pembayaran.pembayaran_page", id_pesanan=id_pesanan)
    
    if is_ajax:
        return jsonify({
            "success": True, 
            "redirect": target_url, 
            "id_pesanan": id_pesanan
        }), 200

    return redirect(target_url)
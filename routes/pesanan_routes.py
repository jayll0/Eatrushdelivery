from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    abort,
    current_app,
    jsonify,
)
from typing import Dict, Any
from .db import get_db_connection
from models.Pesanan import (
    Pesanan,
    get_pesanan_by_user,
    get_pesanan_detail,
    fetch_allowed_statuses,
    get_pesanan_for_seller 
)
from models.Warung import Warung

pesanan_bp = Blueprint("pesanan", __name__)

# --------------------------
# Helpers
# --------------------------

def _get_session_user() -> Dict[str, Any]:
    return session.get("user") or {}

def _get_user_id(user: Dict[str, Any]) -> int:
    return int(user.get("IdPengguna") or user.get("IdUser") or user.get("id") or 0)

def _get_user_role(user_id: int) -> str:
    if not user_id:
        return ""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT Peran FROM Pengguna WHERE IdPengguna=%s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        val = row[0] if isinstance(row, (tuple, list)) else row
        return str(val).lower()
    except Exception:
        current_app.logger.exception("Gagal ambil peran user %s", user_id)
        return ""

def _is_user_seller(user: Dict[str, Any]) -> bool:
    uid = _get_user_id(user)
    role = _get_user_role(uid)
    return role in ("penjual", "seller", "vendor")


# --------------------------
# 1) LIST PESANAN PEMBELI
# --------------------------

@pesanan_bp.route("/pesanan_list", methods=["GET"])
def pesanan_list():
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))

    user = _get_session_user()
    user_id = _get_user_id(user)

    if not user_id:
        flash("User tidak dikenali.", "error")
        return redirect(url_for("home.home"))

    try:
        pesanan_list_res = get_pesanan_by_user(user_id, limit=100)
    except Exception as e:
        current_app.logger.exception("Gagal ambil pesanan user: %s", e)
        pesanan_list_res = []
        flash("Gagal mengambil daftar pesanan.", "error")

    return render_template("listPesanan.html", pesanan_list=pesanan_list_res, user=user)


# --------------------------
# 2) LIST PESANAN PENJUAL
# --------------------------

@pesanan_bp.route('/penjual/pesanan')
def list_pesanan_penjual():
    # 1. Cek Login
    if 'user' not in session or session['user'].get('Peran') != 'penjual':
        return redirect(url_for('auth.auth_page'))

    user = _get_session_user()
    user_id = _get_user_id(user)

    # 2. Ambil IdWarung (PERBAIKAN DISINI)
    conn = get_db_connection()
    
    # Tambahkan buffered=True agar tidak error "Unread result found"
    cur = conn.cursor(dictionary=True, buffered=True) 
    
    try:
        cur.execute("SELECT IdWarung FROM Warung WHERE IdPenjual = %s", (user_id,))
        warung_data = cur.fetchone()
    finally:
        # Sekarang aman untuk ditutup karena data sudah di-buffer
        cur.close()
        conn.close()

    if not warung_data:
        flash("Warung tidak ditemukan.", "error")
        return redirect(url_for('home.home'))

    id_warung = warung_data['IdWarung']
    
    # 3. Ambil Pesanan
    filter_status = request.args.get('status')
    pesanan_list_res = get_pesanan_for_seller(id_warung, filter_status)

    return render_template(
        'listPesananPenjual.html', 
        pesanan=pesanan_list_res, 
        current_status=filter_status,
        user=user
    )
    
@pesanan_bp.route('/penjual/pesanan/<int:id_pesanan>')
def detail_pesanan_warung(id_pesanan):
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # 1. Ambil Data Pesanan & Pembeli
    cur.execute("""
        SELECT pw.*, p.NamaPengguna as NamaPembeli, p.nomorTeleponPengguna, 
               p.Alamat, p.Kordinat, p.Patokan
        FROM PesananWarung pw
        JOIN Pengguna p ON pw.IdPembeli = p.IdPengguna
        WHERE pw.IdPesananWarung = %s
    """, (id_pesanan,))
    pesanan = cur.fetchone()

    if not pesanan:
        cur.close(); conn.close()
        abort(404)

    # === BAGIAN PENTING YANG DITAMBAHKAN ===
    # 2. Ambil Data Warung
    # Kita butuh data ini karena HTML memanggil {{ warung.IdWarung }} untuk gambar profil
    cur.execute("SELECT * FROM Warung WHERE IdWarung = %s", (pesanan['IdWarung'],))
    warung_data = cur.fetchone()
    # =======================================

    # 3. Ambil Item Makanan
    cur.execute("""
        SELECT dp.*, m.NamaMakanan, m.GambarMakanan
        FROM Pesanan dp
        JOIN Makanan m ON dp.IdMakanan = m.IdMakanan
        WHERE dp.IdPesananWarung = %s
    """, (id_pesanan,))
    items = cur.fetchall()

    # --- HITUNG TOTAL ITEM DI SINI ---
    total_item = 0
    for i in items:
        # Menjumlahkan kolom 'BanyakPesanan' dari setiap baris
        total_item += i['BanyakPesanan']
    
    # Masukkan ke variabel pesanan agar bisa dipanggil di HTML
    # Pastikan variabel 'pesanan' sudah didefinisikan sebelumnya (dari query Header)
    if pesanan:
        pesanan['TotalItem'] = total_item

    cur.close()
    conn.close()

    cur.close()
    conn.close()

    status = pesanan['Status']

    # 4. Render Template (Tambahkan warung=warung_data di semua baris)
    if status == 'Menunggu':
        return render_template('menungguPesananWarung.html', pesanan=pesanan, items=items, warung=warung_data)
    elif status == 'Diproses':
        return render_template('menyiapkanPesananWarung.html', pesanan=pesanan, items=items, warung=warung_data)
    elif status == 'Diantar':
        return render_template('mengantarPesananWarung.html', pesanan=pesanan, items=items, warung=warung_data)
    elif status == 'Selesai':
        return render_template('pesananSelesaiWarung.html', pesanan=pesanan, items=items, warung=warung_data)
    else:
        # Default fallback
        return render_template('pesananSelesaiWarung.html', pesanan=pesanan, items=items, warung=warung_data)


# --------------------------
# 3) DETAIL PESANAN UMUM
# --------------------------

@pesanan_bp.route("/pesanan/<int:id_pesanan>")
def pesanan_detail(id_pesanan: int):
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))

    data = get_pesanan_detail(id_pesanan)
    if not data:
        abort(404)

    user = _get_session_user()
    current_uid = _get_user_id(user)
    
    pw = data["pesanan"]
    id_pembeli = int(pw["IdPembeli"] if "IdPembeli" in pw else pw[1])
    
    if id_pembeli == current_uid:
        return render_template("detailPesanan.html",
                               pesanan=pw,
                               details=data["details"],
                               user=user)

    if _is_user_seller(user):
        try:
            id_warung = int(pw["IdWarung"] if "IdWarung" in pw else pw[2])
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT IdPemilik FROM Warung WHERE IdWarung=%s", (id_warung,))
            row = cur.fetchone()
            cur.close()
            conn.close()

            if row:
                pemilik = row[0]
                if int(pemilik) == current_uid:
                    return render_template("detailPesanan.html", 
                                           pesanan=pw,
                                           details=data["details"],
                                           user=user,
                                           is_seller=True)
        except Exception:
            current_app.logger.exception("Gagal cek ownership warung.")

    abort(403)

# --- Tambahkan di dalam routes/pesanan_routes.py ---

@pesanan_bp.route("/penjual/pesanan/<int:id_pesanan>/terima", methods=["POST"])
def terima_pesanan(id_pesanan):
    """
    Mengubah status pesanan menjadi 'Diproses'.
    """
    # 1. Cek Login
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))
    
    # 2. Proses Terima
    try:
        # Menggunakan method update_status dari model Pesanan
        p = Pesanan(id_pesanan=id_pesanan)
        p.update_status("Diproses")
        
        flash("Pesanan berhasil diterima. Status: Diproses.", "success")
    except Exception as e:
        current_app.logger.exception("Gagal terima pesanan: %s", e)
        flash("Gagal memproses pesanan.", "error")

    # 3. Redirect kembali ke halaman Detail Pesanan
    return redirect(url_for('pesanan.list_pesanan_penjual'))

@pesanan_bp.route('/pesanan/<int:id_pesanan>/tolak', methods=['GET', 'POST'])
def tolak_pesanan_page(id_pesanan):
    data = get_pesanan_detail(id_pesanan)
    if not data:
        flash("Pesanan tidak ditemukan", "danger")
        return redirect(url_for('pesanan.list_pesanan_penjual'))

    if request.method == 'POST':
        # Ambil data dari textarea dengan name="alasan"
        alasan = request.form.get('alasan')
        
        pesanan_obj = Pesanan(id_pesanan=id_pesanan)
        
        try:
            if pesanan_obj.tolak_pesanan(alasan):
                flash("Pesanan berhasil ditolak.", "success")
            else:
                flash("Gagal menolak pesanan (Status mungkin sudah berubah).", "warning")
            
            return redirect(url_for('pesanan.list_pesanan_penjual')) # Redirect kembali ke dashboard
            
        except ValueError as e:
            flash(str(e), "danger")
        except Exception as e:
            print(f"Error: {e}")
            flash("Terjadi kesalahan sistem.", "danger")

    # Render template HTML yang Anda buat
    return render_template('pesananDitolak.html', pesanan=data['pesanan'])


@pesanan_bp.route("/penjual/pesanan/<int:id_pesanan>/antar", methods=["POST"])
def antar_pesanan(id_pesanan):
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))
    
    # 2. Proses Terima
    try:
        # Menggunakan method update_status dari model Pesanan
        p = Pesanan(id_pesanan=id_pesanan)
        p.update_status("Diantar")
        
    except Exception as e:
        current_app.logger.exception("Gagal mengubah status pesanan: %s", e)
        flash("Gagal mengubah status pesanan.", "error")

    # 3. Redirect kembali ke halaman Detail Pesanan
    return redirect(url_for('pesanan.list_pesanan_penjual'))


@pesanan_bp.route("/penjual/pesanan/<int:id_pesanan>/selesai", methods=["POST"])
def selesaikan_pesanan(id_pesanan):
    """
    Mengubah status dari 'Diantar' -> 'Selesai'.
    """
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))

    try:
        # 1. Update Status
        p = Pesanan(id_pesanan=id_pesanan)
        p.update_status("Selesai")
        
        # 2. AMBIL DATA LENGKAP (PENTING!)
        # Kita butuh data lengkap (Nama, Harga, dll) untuk ditampilkan di struk/halaman selesai.
        # Objek 'p' di atas tadi cuma punya ID, jadi tidak cukup.
        data_pesanan = get_pesanan_detail(id_pesanan) 
        
        if not data_pesanan:
            flash("Pesanan tidak ditemukan setelah update.", "warning")
            return redirect(url_for('pesanan.list_pesanan_penjual'))

        # 3. Render Template dengan data yang berisi
        # Perhatikan: get_pesanan_detail mengembalikan dict {'pesanan': ..., 'details': ...}
        return render_template('pesananSelesaiWarung.html', pesanan=data_pesanan['pesanan'])

    except Exception as e:
        current_app.logger.exception("Gagal mengubah status pesanan: %s", e)
        flash("Terjadi kesalahan sistem.", "danger")
        return redirect(url_for('pesanan.list_pesanan_penjual'))
        
# --------------------------
# 5) AKSI BATAL PEMBELI
# --------------------------

@pesanan_bp.route("/pesanan/<int:id_pesanan>/batal", methods=["POST"])
@pesanan_bp.route("/pesanan/<int:id_pesanan>/batal", methods=["GET", "POST"])
def batal_pesanan_page(id_pesanan):
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))

    user = session.get("user")
    current_uid = user.get("IdPengguna") or user.get("id") or user.get("IdUser")

    data = get_pesanan_detail(id_pesanan)
    if not data:
        flash("Pesanan tidak ditemukan.", "error")
        return redirect(url_for("pesanan.pesanan_list"))

    pesanan_data = data["pesanan"]
    
    id_pembeli_asli = pesanan_data.get("IdPembeli") or pesanan_data.get("id_pembeli")
    
    if str(id_pembeli_asli) != str(current_uid):
        flash("Anda tidak memiliki akses ke pesanan ini.", "error")
        return redirect(url_for("home.home"))

    if request.method == "POST":
        alasan = request.form.get("alasan")
        
        try:
            p = Pesanan(id_pesanan=id_pesanan)
            
            if p.batalkan_pesanan(alasan):
                flash("Pesanan berhasil dibatalkan.", "success")
            else:
                flash("Gagal membatalkan. Status pesanan sudah berubah (sedang diproses/diantar).", "warning")
                
        except ValueError as e:
            flash(str(e), "warning")
        except Exception as e:
            current_app.logger.exception("Gagal batalkan pesanan: %s", e)
            flash("Terjadi kesalahan sistem.", "error")

        return redirect(url_for("pesanan.pesanan_list"))

    return render_template("pesananDibatalkan.html", pesanan=pesanan_data)


# --------------------------
# 6) HALAMAN SETELAH PEMBAYARAN
# --------------------------

@pesanan_bp.route("/selesai/<int:id_pesanan>")
def pembayaran_selesai(id_pesanan: int):
    data = get_pesanan_detail(id_pesanan)
    pesan = f"Pesanan #{id_pesanan} berhasil diproses." if data else None
    return render_template("pembayaranSelesai.html", pesan=pesan, id_pesanan=id_pesanan)
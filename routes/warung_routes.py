# routes/warung.py
from flask import (
    Blueprint,
    render_template,
    session,
    redirect,
    url_for,
    abort,
    current_app,
    send_file,
    make_response,
    request,
    flash,
    jsonify,
)
import json
import time
from datetime import datetime, timedelta
from io import BytesIO
from models.Warung import Warung
from models.Makanan import Makanan
from .db import get_db_connection
from models.Laporan import ItemLaporan, Laporan


# optional: mysql errors import used in code path
try:
    from mysql.connector import errors as mysql_errors
except Exception:
    mysql_errors = None

warung_bp = Blueprint("warung", __name__)


def _get_session_user_id():
    """Return user id from session with common keys fallback, or None."""
    u = session.get("user") or {}
    return u.get("IdPengguna") or u.get("IdUser") or u.get("id") or None
    
    
def generate_svg_points(values, width=100, height=40):
    if not values: return "0,40 100,40"
    max_val = max(values) if values else 1
    points = []
    padding_top = 5
    count = len(values)
    for i, val in enumerate(values):
        x = 0 if count <= 1 else (i / (count - 1)) * width
        y = height - ((float(val) / float(max_val)) * (height - padding_top))
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)

def require_penjual():
    if 'user' not in session:
        return None, redirect(url_for('auth.auth_page'))

    user = session.get('user') or {}
    if user.get('Peran') != 'penjual':
        flash("Akses khusus penjual.", "danger")
        return None, redirect(url_for('home.home'))

    user_id = _get_session_user_id()
    if not user_id:
        return None, redirect(url_for('auth.auth_page'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT * FROM Warung WHERE IdPenjual=%s LIMIT 1",
            (user_id,)
        )
        warung = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not warung:
        flash("Anda belum memiliki warung.", "warning")
        return None, redirect(url_for('warung.pendaftaran_warung'))

    return warung, None


@warung_bp.route("/penjual/pendaftaranWarung")
def pendaftaran_warung():
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))

    return render_template("pendaftaranWarung.html")

@warung_bp.route("/penjual/warung")
def home_warung():
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))

    id_penjual = _get_session_user_id()
    if not id_penjual:
        flash("Anda belum memiliki warung. Silahkan daftarkan warung anda.", "error")
        return redirect(url_for("pendaftaran_warung"))

    warung_data = {}
    keuangan_data = {'total_pendapatan': 0, 'total_transaksi': 0}
    chart_rows = []
    polyline_str = "0,40 100,40"
    makanan_data = []

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute("""
            SELECT IdWarung, NamaWarung, AlamatWarung, Rating, 
                   GambarWarung, KordinatWarung
            FROM Warung
            WHERE IdPenjual=%s LIMIT 1
        """, (id_penjual,))
        
        fetched_warung = cur.fetchone()
        if not fetched_warung:
            return redirect(url_for('warung.pendaftaran_warung'))

        warung_data = fetched_warung
        id_warung = warung_data['IdWarung']

        try:
            makanan_db_list = Makanan().get_by_warung(id_warung) or []
            
            for m in makanan_db_list:
                gambar = None
                if m.get_gambar_makanan():
                    if "warung.makanan_image" in current_app.view_functions:
                        gambar = url_for("warung.makanan_image", id_m=m.get_id_makanan())
                    else:
                        gambar = url_for("home.makanan_gambar", id_makanan=m.get_id_makanan())
                else:
                    gambar = url_for('static', filename='img/noimage.png')

                makanan_data.append({
                    "IdMakanan": m.get_id_makanan(),
                    "NamaMakanan": m.get_nama_makanan(),
                    "HargaMakanan": m.get_harga_makanan(),
                    "DetailMakanan": m.get_deskripsi_makanan(),
                    "Stok": m.get_stok_makanan(),
                    "GambarMakanan": gambar
                })
        except Exception as e:
            current_app.logger.warning(f"Gagal memuat list makanan: {e}")
        try:
            try:
                jumlah_hari = int(request.args.get('days', 7))
            except (ValueError, TypeError):
                jumlah_hari = 7 
            today = datetime.now().date()
            start_date = today - timedelta(days=jumlah_hari - 1)
            cur.execute("""
                SELECT IdPesananWarung, TotalHarga, Status, DibuatPada 
                FROM PesananWarung 
                WHERE IdWarung = %s
            """, (id_warung,))
            raw_orders = cur.fetchall()

            list_transaksi = []
            for row in raw_orders:
                list_transaksi.append(ItemLaporan(
                    id_pesanan=row['IdPesananWarung'],
                    total_harga=row['TotalHarga'],
                    status=row['Status'],
                    dibuat_pada=row['DibuatPada']
                ))
            
            laporan = Laporan(id_warung=id_warung, transaksi_list=list_transaksi)

            keuangan_data = {
                'total_pendapatan': laporan.getTotalPendapatan(start_date),
                'total_transaksi': laporan.getTotalPesanan(start_date)
            }
            
            data_harian = laporan.sortPesanan() or {}
            nilai_grafik = []
            step = 1
            if jumlah_hari > 30:
                step = 14 
            elif jumlah_hari > 7:
                step = 5 
            current_date = start_date
            idx = 0 
            
            while current_date <= today:
                tgl_str = current_date.strftime('%Y-%m-%d')
                total = data_harian.get(tgl_str, 0)
                nilai_grafik.append(total)
                if idx == 0 or current_date == today or idx % step == 0:
                     tgl_pendek = current_date.strftime('%d/%m')
                     chart_rows.append({'tgl': tgl_pendek, 'total': total})
                
                current_date += timedelta(days=1)
                idx += 1
                
            polyline_str = generate_svg_points(nilai_grafik)
                
        except Exception as e:
            current_app.logger.warning(f"Gagal memuat statistik: {e}")

    except Exception as e:
        current_app.logger.exception("Gagal memuat dashboard utama: %s", e)
        flash("Terjadi kesalahan sistem.", "danger")
        
    finally:
        if cur: cur.close()
        if conn: conn.close()

    return render_template("homeWarung.html", 
                            warung=warung_data,
                           keuangan=keuangan_data, 
                           makanan=makanan_data,    
                           chart_rows=chart_rows, 
                           chart_polyline=polyline_str)

@warung_bp.route("/warung/<int:id_warung>")
def warung_detail(id_warung):
    # 1. Cek Login
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))

    # 2. Ambil Data Warung
    warung_obj = Warung().get_by_id(id_warung)
    if not warung_obj:
        abort(404)

    # 3. Ambil Data Makanan
    try:
        makanan_db_list = Makanan().get_by_warung(id_warung) or []
    except Exception:
        makanan_db_list = []

    # --- SETUP TIMESTAMP UNTUK CACHE BUSTING ---
    # Kita buat satu angka waktu unik untuk request ini
    ts = int(time.time()) 
    # -------------------------------------------

    # 4. Format Data Warung (Untuk HTML)
    gambar_warung_url = None
    if warung_obj.get_gambar_warung():
        # Cek route mana yang tersedia untuk gambar
        if "warung.warung_image" in current_app.view_functions:
            # PERHATIKAN: Saya menambahkan parameter v=ts di sini
            gambar_warung_url = url_for("warung.warung_image", id_warung=warung_obj.get_id_warung(), v=ts)
        else:
            # Di sini juga ditambahkan v=ts
            gambar_warung_url = url_for("home.warung_gambar", id_warung=warung_obj.get_id_warung(), v=ts)

    warung_data = {
        "IdWarung": warung_obj.get_id_warung(),
        "IdPenjual": warung_obj.get_id_penjual(),
        "NamaWarung": warung_obj.get_nama_warung(),
        "AlamatWarung": warung_obj.get_alamat_warung(),
        "Rating": warung_obj.get_rating_warung(),
        "GambarToko": gambar_warung_url, 
        "Kordinat": warung_obj.get_kordinat_warung() if hasattr(warung_obj, "get_kordinat_warung") else None
    }

    # 5. Format Data Makanan List (Untuk Loop di HTML)
    makanan_data = []
    for m in makanan_db_list:
        # Generate URL Gambar Makanan
        gambar_makanan_url = None
        if m.get_gambar_makanan():
            if "warung.makanan_image" in current_app.view_functions:
                # PERHATIKAN: Saya menambahkan parameter v=ts di sini juga
                gambar_makanan_url = url_for("warung.makanan_image", id_m=m.get_id_makanan(), v=ts)
            else:
                gambar_makanan_url = url_for("home.makanan_gambar", id_makanan=m.get_id_makanan(), v=ts)
        
        # Masukkan ke list dictionary
        makanan_data.append({
            "IdMakanan": m.get_id_makanan(),
            "NamaMakanan": m.get_nama_makanan(),
            "HargaMakanan": m.get_harga_makanan(),
            "DetailMakanan": m.get_deskripsi_makanan(),
            "Stok": m.get_stok_makanan(),
            "GambarMakanan": gambar_makanan_url
        })

    # 6. Render Template
    return render_template("warung.html", warung=warung_data, makanan_list=makanan_data)

@warung_bp.route("/makanan/<int:id_m>")
def makanan_detail(id_m):
    m = Makanan().get_by_id(id_m)
    if not m:
        abort(404)

    makanan_data = {
        "IdMakanan": m.get_id_makanan(),
        "NamaMakanan": m.get_nama_makanan(),
        "HargaMakanan": m.get_harga_makanan(),
        "DetailMakanan": m.get_deskripsi_makanan(),
        "Stok": m.get_stok_makanan(),
        "IdWarung": m.get_id_warung(),
        "GambarMakanan": None # Default
    }


    try:
        if m.get_gambar_makanan():
            makanan_data["GambarMakanan"] = url_for("warung.makanan_image", id_m=m.get_id_makanan())
        else:
            makanan_data["GambarMakanan"] = url_for('static', filename='img/noimage.png') 
    except Exception:
        makanan_data["GambarMakanan"] = url_for('static', filename='img/noimage.png')

    # Render template dengan variabel 'makanan' yang berisi dict lengkap
    return render_template("detailMakanan.html", makanan=makanan_data)


@warung_bp.route("/makanan/gambar/<int:id_m>")
def makanan_image(id_m):
    m = Makanan().get_by_id(id_m)
    if not m or not m.get_gambar_makanan():
        abort(404)
    try:
        img_bytes = m.get_gambar_makanan()
        buf = BytesIO(img_bytes)
        mime = getattr(m, "get_mime_gambar", lambda: None)() or "application/octet-stream"
        resp = make_response(send_file(buf, mimetype=mime))
        size = getattr(m, "get_size_gambar", lambda: None)() or len(img_bytes)
        resp.headers["Content-Length"] = str(size)
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    except Exception:
        current_app.logger.exception("Gagal kirim gambar makanan")
        abort(404)


@warung_bp.route("/warung/gambar/<int:id_warung>")
def warung_image(id_warung):
    w = Warung().get_by_id(id_warung)
    if not w or not w.get_gambar_warung():
        abort(404)
    try:
        img_bytes = w.get_gambar_warung()
        buf = BytesIO(img_bytes)
        mime = getattr(w, "get_mime_gambar", lambda: None)() or "application/octet-stream"
        resp = make_response(send_file(buf, mimetype=mime))
        size = getattr(w, "get_size_gambar", lambda: None)() or len(img_bytes)
        resp.headers["Content-Length"] = str(size)
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    except Exception:
        current_app.logger.exception("Gagal kirim gambar warung")
        abort(404)


@warung_bp.route("/warung/daftar", methods=["GET"])
def daftar_warung_page():
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))
    return render_template("daftarWarung.html", user=session.get("user"))


@warung_bp.route("/warung/daftar", methods=["POST"])
def daftar_warung_submit():
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))

    nama = (request.form.get("nama_warung") or "").strip()
    alamat = (request.form.get("alamat_warung") or "").strip()
    jam_buka = (request.form.get("jam_buka") or "").strip() or None
    jam_tutup = (request.form.get("jam_tutup") or "").strip() or None
    kordinat = (request.form.get("kordinat") or "").strip() or None 

    if not nama:
        flash("Nama warung wajib diisi.", "danger")
        return render_template("daftarWarung.html", user=session.get("user"), form_data=request.form)

    user_id = _get_session_user_id()
    if not user_id:
        flash("Tidak dapat menentukan identitas pengguna. Silakan login ulang.", "danger")
        return redirect(url_for("auth.auth_page"))

    # Buat instance Warung
    w = Warung(id_penjual=user_id, nama_warung=nama, alamat_warung=alamat)

    file = request.files.get("gambar")
    if file and file.filename:
        try:
            file_bytes = file.read()
            if file_bytes:
                try:
                    w.set_gambar_from_upload(file_bytes, save_to_db=False) # Jangan save ke DB dulu karena ID belum ada
                except Exception:
                    # Fallback manual jika method helper gagal/beda nama
                    try:
                        w._gambar_warung = file_bytes
                    except Exception:
                        pass
        except Exception:
            current_app.logger.warning("Gagal membaca file gambar", exc_info=True)

    try:
        # Simpan Warung Baru
        new_id = w.save_new()

        # Update data tambahan (Jam & Koordinat) & simpan gambar jika tadi belum tersimpan di save_new
        if new_id:
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                # Update kolom tambahan
                cur.execute(
                    "UPDATE Warung SET JamBuka=%s, JamTutup=%s, KordinatWarung=%s WHERE IdWarung=%s",
                    (jam_buka, jam_tutup, kordinat, new_id),
                )
                
                # Jika gambar diset di object tapi belum tersimpan (karena save_new mungkin tidak include blob di insert pertama)
                # Kita pastikan update gambar di sini
                if w.get_gambar_warung():
                     cur.execute(
                        "UPDATE Warung SET GambarWarung=%s WHERE IdWarung=%s",
                        (w.get_gambar_warung(), new_id)
                     )

                conn.commit()
            except Exception:
                conn.rollback()
                current_app.logger.warning("Gagal update data tambahan warung", exc_info=True)
            finally:
                cur.close()
                conn.close()

        # Update role pengguna -> penjual
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("UPDATE Pengguna SET Peran=%s WHERE IdPengguna=%s", ("penjual", user_id))
            conn.commit()

            # Update session user agar tidak perlu logout-login
            session_user = session.get("user", {})
            session_user["Peran"] = "penjual"
            session["user"] = session_user
        except Exception:
            conn.rollback()
        finally:
            cur.close()
            conn.close()

        flash("Pendaftaran warung berhasil!", "success")
        
        # === REVISI DI SINI: Redirect ke Dashboard Penjual ===
        return redirect(url_for("warung.home_warung")) 

    except Exception as e:
        current_app.logger.exception("Gagal mendaftar warung: %s", e)
        flash("Gagal mendaftar warung. Silakan coba lagi.", "danger")
        return render_template("daftarWarung.html", user=session.get("user"), form_data=request.form)


@warung_bp.route("/warung/search")
def warung_search():
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "").strip()
    try:
        page = int(request.args.get("page", 1))
    except Exception:
        page = 1
    try:
        per_page = int(request.args.get("per_page", 20))
    except Exception:
        per_page = 20
    offset = (page - 1) * per_page

    results = []

    if q:
        results = Warung().search_by_name(q, limit=per_page, offset=offset)
    else:
        if sort in ("sold_high", "sold_low"):
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            try:
                order_dir = "DESC" if sort == "sold_high" else "ASC"
                sql = f"""
                    SELECT w.IdWarung, w.IdPenjual, w.NamaWarung, w.AlamatWarung,
                           w.NomorTeleponWarung, w.GambarWarung, w.Rating, w.KordinatWarung,
                           w.MimeGambarWarung, w.SizeGambarWarung,
                           COALESCE(s.total_sold, 0) AS total_sold
                    FROM Warung w
                    LEFT JOIN (
                        SELECT m.IdWarung AS IdWarung, SUM(p.BanyakPesanan) AS total_sold
                        FROM Pesanan p
                        JOIN Makanan m ON p.IdMakanan = m.IdMakanan
                        GROUP BY m.IdWarung
                    ) s ON s.IdWarung = w.IdWarung
                    ORDER BY total_sold {order_dir}, w.NamaWarung ASC
                    LIMIT %s OFFSET %s
                """
                cur.execute(sql, (per_page, offset))
                rows = cur.fetchall() or []
                for row in rows:
                    w = Warung(
                        id_warung=row.get("IdWarung"),
                        id_penjual=row.get("IdPenjual"),
                        nama_warung=row.get("NamaWarung"),
                        alamat_warung=row.get("AlamatWarung"),
                        nomor_telepon_warung=row.get("NomorTeleponWarung"),
                        gambar_warung=row.get("GambarWarung"),
                        rating_warung=row.get("Rating") or 0.0,
                        kordinat_warung=row.get("KordinatWarung"),
                        mime_gambar=row.get("MimeGambarWarung"),
                        size_gambar=row.get("SizeGambarWarung"),
                    )
                    setattr(w, "_total_sold", row.get("total_sold", 0))
                    results.append(w)
            except Exception:
                # fallback to generic get_all if query fails
                try:
                    results = Warung().get_all(limit=per_page, offset=offset)
                except Exception:
                    results = []
            finally:
                try:
                    cur.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass
        else:
            sort_opt = None
            if sort == "highest":
                sort_opt = "highest"
            elif sort == "lowest":
                sort_opt = "lowest"
            try:
                results = Warung().get_all(limit=per_page, offset=offset, sort_by_rating=sort_opt)
            except Exception:
                results = []

    warungs = []
    for w in results:
        try:
            gambar = None
            if getattr(w, "get_gambar_warung", None) and w.get_gambar_warung():
                if "warung.warung_image" in current_app.view_functions:
                    gambar = url_for("warung.warung_image", id_warung=w.get_id_warung())
                elif "home.warung_gambar" in current_app.view_functions:
                    gambar = url_for("home.warung_gambar", id_warung=w.get_id_warung())
        except Exception:
            gambar = None

        warungs.append(
            {
                "IdWarung": w.get_id_warung(),
                "NamaWarung": w.get_nama_warung(),
                "AlamatWarung": w.get_alamat_warung(),
                "Rating": w.get_rating_warung(),
                "GambarToko": gambar,
                "total_sold": getattr(w, "_total_sold", None),
            }
        )
    return render_template("search_results.html", warungs=warungs, query=q, sort=sort, page=page)





@warung_bp.route("/makanan/edit/<int:id_m>", methods=["GET", "POST"])
def makanan_edit(id_m):
    # 1. Cek Login
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))
    
    # 2. Ambil Data Makanan
    m = Makanan().get_by_id(id_m)
    if not m:
        abort(404)

    # === LOGIKA GET: Tampilkan Halaman Edit ===
    if request.method == "GET":
        # Siapkan URL Gambar agar preview muncul
        gambar_url = url_for('static', filename='img/noimage.png')
        if m.get_gambar_makanan():
             # Sesuaikan dengan nama fungsi endpoint gambar Anda
             if "warung.makanan_image" in current_app.view_functions:
                gambar_url = url_for("warung.makanan_image", id_m=m.get_id_makanan())
             else:
                gambar_url = url_for("home.makanan_gambar", id_makanan=m.get_id_makanan())

        return render_template("editMakananWarung.html", makanan=m, gambar_url=gambar_url)

    # === LOGIKA POST: Simpan Perubahan ===
    # Ambil data dari form HTML (pastikan atribut name="..." di HTML sesuai)
    nama = (request.form.get("nama") or m.get_nama_makanan()).strip()
    harga = request.form.get("harga", m.get_harga_makanan())
    deskripsi = request.form.get("deskripsi", m.get_deskripsi_makanan())
    
    try:
        stok = int(request.form.get("stok", m.get_stok_makanan()) or 0)
    except Exception:
        stok = m.get_stok_makanan() or 0
    
    file = request.files.get("gambar") # Ambil file upload

    try:
        # Update Data Teks
        # Pastikan method update_info ada di Model Makanan, jika tidak gunakan setter manual
        try:
            m.update_info(nama=nama, harga=float(harga or 0), deskripsi=deskripsi, stok=stok)
        except AttributeError:
            # Fallback jika tidak ada update_info
            m.set_nama_makanan(nama)
            m.set_harga_makanan(float(harga or 0))
            m.set_deskripsi_makanan(deskripsi)
            m.set_stok_makanan(stok)

        m.save_update() # Simpan ke DB

        # Update Gambar (Jika user upload gambar baru)
        if file and file.filename:
            data = file.read()
            try:
                m.set_gambar_from_upload(data, save_to_db=True)
            except Exception:
                try:
                    m.set_gambar_makanan(data)
                    # Perlu save manual jika set_gambar_makanan tidak auto-save
                    # m.save_update() 
                except Exception:
                    pass
        
        # Update Rating Warung (Opsional)
        w = Warung().get_by_id(m.get_id_warung())
        if w:
            try:
                w.set_rating_warung()
            except Exception:
                pass
        
        flash("Makanan berhasil diperbarui.", "success")
        
        # === PERUBAHAN DI SINI ===
        # Redirect ke Home Warung (Daftar Warung Penjual)
        return redirect(url_for("warung.home_warung")) 

    except Exception as e:
        current_app.logger.exception("Gagal update makanan: %s", e)
        flash("Gagal update makanan.", "danger")
        # Jika gagal, kembalikan ke halaman edit
        return render_template("editMakananWarung.html", makanan=m, gambar_url=url_for('static', filename='img/noimage.png'))


@warung_bp.route("/makanan/delete/<int:id_m>", methods=["POST"])
def makanan_delete(id_m):
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))
    m = Makanan().get_by_id(id_m)
    if not m:
        abort(404)
    user_id = _get_session_user_id()
    if user_id and m.get_id_warung():
        w = Warung().get_by_id(m.get_id_warung())
        if w and w.get_id_penjual() != user_id:
            abort(403)
    try:
        rc = m.delete()
        if m.get_id_warung():
            w = Warung().get_by_id(m.get_id_warung())
            if w:
                try:
                    w.set_rating_warung()
                except Exception:
                    pass
        flash("Makanan dihapus.", "success")
        return redirect(request.referrer or url_for("home.home"))
    except Exception as e:
        current_app.logger.exception("Gagal hapus makanan: %s", e)
        flash("Gagal hapus makanan.", "danger")
        return redirect(request.referrer or url_for("home.home"))





@warung_bp.route("/warung/set_rating/<int:id_warung>", methods=["POST"])
def warung_set_rating(id_warung):
    w = Warung().get_by_id(id_warung)
    if not w:
        abort(404)
    try:
        new_rating = w.set_rating_warung()
        return jsonify({"rating": new_rating})
    except Exception as e:
        current_app.logger.exception("Gagal set rating warung: %s", e)
        return jsonify({"error": "gagal"}), 500
        

# Alamat

@warung_bp.route("/penjual/alamat")
def alamat_warung():
    user_id = _get_session_user_id()
    if not user_id:
        return redirect(url_for('auth.auth_page'))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT KordinatWarung, AlamatWarung 
            FROM Warung 
            WHERE IdPenjual = %s 
            LIMIT 1
        """, (user_id,))
        data = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    # Jika user login tapi belum daftar warung
    if not data:
        flash("Anda belum memiliki warung. Silakan daftar terlebih dahulu.", "warning")
        return redirect(url_for('warung.pendaftaran_warung'))

    # 3. Siapkan variabel untuk template
    # Menggunakan key sesuai kolom database Warung
    current_kordinat = data['KordinatWarung'] if data['KordinatWarung'] else ''
    current_patokan = data['AlamatWarung'] if data['AlamatWarung'] else ''

    # 4. Render Template
    # Pastikan 'editAlamatPengguna.html' form-nya mengarah ke url 'warung.simpan_alamat_warung'
    return render_template('editAlamatWarung.html', 
                           current_kordinat=current_kordinat, 
                           current_patokan=current_patokan)


# @warung_bp.route("/penjual/simpan-alamat/<int:id_warung>", methods=['POST'])
# def simpan_alamat_warung(id_warung):
#     if 'user' not in session:
#         return jsonify({'status': 'unauthorized'}), 401

#     user_id = _get_session_user_id()
#     if not user_id:
#         return jsonify({'status': 'unauthorized'}), 401

#     w = Warung().get_by_id(id_warung)
#     if not w:
#         return jsonify({'status': 'not_found'}), 404

#     if w.get_id_penjual() != user_id:
#         return jsonify({'status': 'forbidden'}), 403

#     kordinat = request.form.get('kordinat')
#     alamat = request.form.get('alamat')

#     if not kordinat:
#         return jsonify({'status': 'invalid'}), 400

#     w.update_lokasi(kordinat, alamat)
#     return jsonify({'status': 'success'})

        

# Tambah makanan
@warung_bp.route("/penjual/makanan/tambah/<int:id_warung>")
def makanan_tambah(id_warung):
    # 1. Cek Login
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))

    # 2. Ambil Data Warung
    # Asumsi: Warung().get_by_id mengembalikan objek atau dictionary
    warung_obj = Warung().get_by_id(id_warung)
    if not warung_obj:
        abort(404)

    # 3. Ambil Data Makanan
    try:
        makanan_db_list = Makanan().get_by_warung(id_warung) or []
    except Exception:
        makanan_db_list = []

    # 4. Format Data Warung (Untuk HTML)
    # Kita rapikan logika URL gambar disini agar HTML tinggal pakai
    gambar_warung_url = None
    # if warung_obj.get_gambar_warung():
    #     # Cek route mana yang tersedia untuk gambar
    #     if "warung.warung_image" in current_app.view_functions: 
    #         gambar_warung_url = url_for("warung.warung_image", id_warung=warung_obj.get_id_warung())
    #     else:
    #         gambar_warung_url = url_for("home.warung_gambar", id_warung=warung_obj.get_id_warung())

    warung_data = {
        "IdWarung": warung_obj.get_id_warung(),
        "IdPenjual": warung_obj.get_id_penjual(),
        "NamaWarung": warung_obj.get_nama_warung(),
        "AlamatWarung": warung_obj.get_alamat_warung(),
        "Rating": warung_obj.get_rating_warung(),
        # "GambarToko": gambar_warung_url, # URL sudah siap pakai
        "Kordinat": warung_obj.get_kordinat_warung() if hasattr(warung_obj, "get_kordinat_warung") else None
    }

    # 5. Format Data Makanan List (Untuk Loop di HTML)
    makanan_data = []
    for m in makanan_db_list:
        # Generate URL Gambar Makanan
        gambar_makanan_url = None
        if m.get_gambar_makanan():
            if "warung.makanan_image" in current_app.view_functions:
                gambar_makanan_url = url_for("warung.makanan_image", id_m=m.get_id_makanan())
            else:
                gambar_makanan_url = url_for("home.makanan_gambar", id_makanan=m.get_id_makanan())
        
        # Masukkan ke list dictionary
        makanan_data.append({
            "IdMakanan": m.get_id_makanan(),
            "NamaMakanan": m.get_nama_makanan(),
            "HargaMakanan": m.get_harga_makanan(),
            "DetailMakanan": m.get_deskripsi_makanan(),
            "Stok": m.get_stok_makanan(),
            "GambarMakanan": gambar_makanan_url # URL siap pakai
        })

    # 6. Render Template
    # Mengirim 'warung' (dict) dan 'makanan_list' (list of dicts)
    return render_template("tambahMakananWarung.html", warung=warung_data, makanan_list=makanan_data)

@warung_bp.route("/makanan/tambah", methods=["GET", "POST"])
def tambah_makanan_submit():
    # 1. Cek Login
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))

    # 2. Cari Warung milik User yang login
    user_id = _get_session_user_id()
    
    # === PERBAIKAN DB: Mengatasi "Unread result found" ===
    conn = get_db_connection()
    # Gunakan buffered=True dan fetchall() untuk menguras buffer sepenuhnya
    cur = conn.cursor(dictionary=True, buffered=True)
    
    warung_data = None
    try:
        cur.execute("SELECT IdWarung FROM Warung WHERE IdPenjual = %s LIMIT 1", (user_id,))
        results = cur.fetchall() # Ambil semua (walau cuma 1) agar buffer bersih
        if results:
            warung_data = results[0]
    finally:
        cur.close()
        conn.close()
    # ======================================================

    if not warung_data:
        flash("Anda belum memiliki warung. Silakan daftar dulu.", "warning")
        return redirect(url_for('warung.pendaftaran_warung'))

    id_warung = warung_data['IdWarung']

    # === LOGIKA GET: Tampilkan Form ===
    if request.method == "GET":
        return render_template("tambahMakanan.html", id_warung=id_warung)

    # === LOGIKA POST: Proses Data ===
    
    # 1. Bersihkan Input (Logic dari referensi)
    nama = (request.form.get("nama") or "").strip()
    harga = (request.form.get("harga") or "0").strip()
    deskripsi = (request.form.get("deskripsi") or "").strip()
    
    try:
        stok = int(request.form.get("stok", "0").strip() or 0)
    except Exception:
        stok = 0

    file = request.files.get("gambar")

    try:
        # 2. Instansiasi & Set Data
        m = Makanan()
        m.set_id_warung(id_warung)
        m.set_nama_makanan(nama)
        m.set_harga_makanan(float(harga or 0))
        m.set_deskripsi_makanan(deskripsi)
        m.set_stok_makanan(stok)

        # 3. Simpan Data Utama
        m.save_new() 

        # 4. Handle Gambar (Logic Try-Except Bertingkat dari referensi)
        if file and file.filename:
            data = file.read()
            try:
                # Prioritas 1: Upload dengan resize/format (jika method ada)
                m.set_gambar_from_upload(data, save_to_db=True)
            except Exception:
                # Prioritas 2: Fallback ke simpan blob raw
                try:
                    m.set_gambar_makanan(data)
                    m.save_update() # Update record yang baru dibuat
                except Exception:
                    pass
        
        # 5. Update Rating Warung
        try:
            w = Warung().get_by_id(id_warung)
            if w:
                w.set_rating_warung()
        except Exception:
            pass
        
        flash("Makanan berhasil ditambahkan.", "success")
        return redirect(url_for("warung.home_warung"))

    except Exception as e:
        current_app.logger.exception("Gagal tambah makanan: %s", e)
        flash("Gagal menambah makanan.", "danger")
        # Kembalikan ke form jika gagal agar user tidak perlu mengetik ulang (opsional)
        return render_template("tambahMakanan.html", id_warung=id_warung)

    except Exception as e:
        current_app.logger.exception("Gagal tambah makanan: %s", e)
        flash("Gagal menambah makanan.", "danger")
        return render_template("tambahMakanan.html", id_warung=id_warung)
        
@warung_bp.route("/penjual/makanan/form-tambah/<int:id_warung>")
def tambah_makanan_page(id_warung):
    if "user" not in session:
        return redirect(url_for("auth.auth_page"))
        
    return render_template("tambahMakanan.html", id_warung=id_warung)

def _get_session_warung_id():
    """Mengambil IdWarung langsung dari session user."""
    user = session.get("user") or {}
    # Cek berbagai kemungkinan penulisan key di session
    return user.get("IdWarung") or user.get("id_warung") or user.get("Idwarung")

# ==========================================
# 1. PROFIL WARUNG
# ==========================================
@warung_bp.route('/penjual/profil')
def profil_warung():

    warung, redirect_resp = require_penjual()
    if redirect_resp:
        return redirect_resp


    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT Email FROM Pengguna WHERE IdPengguna = %s", (warung['IdPenjual'],))
        data_pengguna = cur.fetchone()
        warung['Email'] = data_pengguna['Email'] if data_pengguna else None
    finally:
        cur.close()
        conn.close()

    return render_template('profilWarung.html', warung=warung)



@warung_bp.route("/penjual/editProfil", methods=['GET', 'POST'])
def edit_profil_warung():
    # 1. Cek Login & Validasi
    warung_data, redirect_resp = require_penjual()
    if redirect_resp:
        return redirect_resp

    # 2. Ambil Object Warung
    w = Warung().get_by_id(warung_data['IdWarung'])
    if not w:
        flash("Data warung error.", "danger")
        return redirect(url_for('warung.profil_warung'))

    # === [GET] TAMPILKAN FORM ===
    if request.method == 'GET':
        # Inject URL gambar untuk HTML (agar bisa pakai warung.GambarToko)
        warung_data['GambarToko'] = url_for('warung.warung_profil_image', id_warung=warung_data['IdWarung'])
        return render_template('editProfilWarung.html', warung=warung_data)

    # === [POST] PROSES DATA ===
    nama = request.form.get('nama_warung')
    telp = request.form.get('nomor_telepon') 
    alamat = request.form.get('alamat_warung')
    jam_buka = request.form.get('jam_buka')
    jam_tutup = request.form.get('jam_tutup')

    # A. Update Data Teks ke Object
    if nama: w.set_nama_warung(nama)
    if alamat: w.set_alamat_warung(alamat)
    if telp: w.set_nomor_telepon_warung(telp)

    # B. Handle File Gambar (Hanya baca & set ke object, JANGAN save ke DB dulu)
    file = request.files.get('gambar')
    ada_gambar_baru = False # Flag penanda

    if file and file.filename:
        try:
            data_gambar = file.read()
            # Set ke memori object saja (save_to_db=False)
            try:
                w.set_gambar_from_upload(data_gambar, save_to_db=False)
            except:
                w.set_gambar_warung(data_gambar)
            
            ada_gambar_baru = True
        except Exception as e:
            current_app.logger.error(f"Gagal membaca file gambar: {e}")

    # C. Simpan Data Dasar (Nama, Alamat, Telp) lewat Model
    w.save_update()

    # D. Simpan Data Tambahan & Gambar (MANUAL QUERY - Sesuai Request Anda)
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1. Update Jam Buka & Tutup
        cur.execute(
            "UPDATE Warung SET JamBuka=%s, JamTutup=%s WHERE IdWarung=%s", 
            (jam_buka or None, jam_tutup or None, w.get_id_warung())
        )

        # 2. Update Gambar (Hanya jika ada upload baru)
        # Logika ini sama persis dengan potongan kode pendaftaran yang Anda kirim
        if ada_gambar_baru and w.get_gambar_warung():
             cur.execute(
                "UPDATE Warung SET GambarWarung=%s WHERE IdWarung=%s",
                (w.get_gambar_warung(), w.get_id_warung())
             )
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Gagal update data tambahan/gambar warung: {e}")
        flash("Gagal menyimpan detail tambahan.", "warning")
    finally:
        cur.close()
        conn.close()

    flash("Profil warung berhasil diperbarui.", "success")
    return redirect(url_for('warung.profil_warung'))

@warung_bp.route('/warung/foto_profil/<int:id_warung>')
def warung_profil_image(id_warung):
    w = Warung().get_by_id(id_warung)
    if not w or not w.get_gambar_warung():
        return redirect(url_for('static', filename='img/noimage.png'))

    img_bytes = w.get_gambar_warung()
    buf = BytesIO(img_bytes)
    mime = getattr(w, "get_mime_gambar", lambda: None)() or "image/jpeg"

    resp = make_response(send_file(buf, mimetype=mime))
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@warung_bp.route("/penjual/menu")
def menu_penjual():
    warung, redirect_resp = require_penjual()
    if redirect_resp:
        return redirect_resp

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT Email FROM Pengguna WHERE IdPengguna = %s", (warung['IdPenjual'],))
        data_pengguna = cur.fetchone()
        
        if data_pengguna:
            warung['Email'] = data_pengguna['Email']
        else:
            warung['Email'] = None
            
    except Exception as e:
        current_app.logger.error(f"Gagal mengambil email warung: {e}")
        warung['Email'] = None
    finally:
        cur.close()
        conn.close()

    # Sekarang variabel 'warung' yang dikirim ke HTML sudah berisi key 'Email'
    return render_template('menuPenjual.html', warung=warung)



@warung_bp.route("/penjual/edit-alamat/<int:id_warung>")
def edit_alamat_page(id_warung):
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))

    user_id = _get_session_user_id()
    if not user_id:
        return redirect(url_for('auth.auth_page'))

    w = Warung().get_by_id(id_warung)
    if not w:
        flash("Warung tidak ditemukan.", "error")
        return redirect(url_for('warung.profil_warung'))

    if w.get_id_penjual() != user_id:
        abort(403)

    curr_alamat = w.get_alamat_warung()
    curr_kordinat = (
        w.get_kordinat_warung()
        if hasattr(w, 'get_kordinat_warung')
        else None
    )

    # Variabel yang dikirim: 'current_alamat' (Bukan current_patokan)
    return render_template(
        'editAlamatWarung.html',
        warung=w,
        current_alamat=curr_alamat,
        current_kordinat=curr_kordinat
    )



@warung_bp.route("/penjual/simpan-alamat-ajax/<int:id_warung>", methods=['POST'])
def simpan_alamat_warung(id_warung): # Nama fungsi disamakan dengan url_for di HTML
    
    # 1. Cek Login User
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Sesi habis, silakan login ulang'}), 401

    user_id = _get_session_user_id()
    if not user_id:
        return jsonify({'status': 'error', 'message': 'User tidak valid'}), 401

    # 2. Validasi Kepemilikan Warung (Security Check)
    # Kita cek apakah id_warung yang dikirim URL benar milik user yang login
    w = Warung().get_by_id(id_warung)
    if not w:
        return jsonify({'status': 'error', 'message': 'Warung tidak ditemukan'}), 404
    
    if w.get_id_penjual() != user_id:
        return jsonify({'status': 'error', 'message': 'Anda tidak memiliki akses ke warung ini'}), 403
    
    # 3. Ambil Data Form
    kordinat = request.form.get('kordinat')
    alamat = request.form.get('alamat') 
    # patokan = request.form.get('patokan') # Opsional, jika di DB Warung tidak ada kolom patokan, abaikan

    if not kordinat:
        return jsonify({'status': 'error', 'message': 'Koordinat wajib diisi'}), 400

    try:
        # 4. Update Database
        # Kita pakai instance 'w' yang sudah di-get di atas
        w.update_lokasi(kordinat, alamat) 

        # --- PERBAIKAN LOGIC SESSION ---
        # JANGAN update session['user']['Alamat'] karena itu alamat pribadi user.
        # Kecuali Anda menyimpan data warung spesifik di session['warung_active'].
        # Untuk keamanan data, lebih baik biarkan session user tetap data user.
        
        return jsonify({'status': 'success'})

    except Exception as e:
        current_app.logger.error(f"Gagal simpan alamat warung: {e}")
        return jsonify({'status': 'error', 'message': 'Terjadi kesalahan sistem'}), 500



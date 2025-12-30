from flask import Blueprint, render_template, session, redirect, url_for, request, send_file, make_response, abort, current_app, jsonify
from io import BytesIO
from models.Pengguna import Pengguna
from .db import get_db_connection

pengguna_bp = Blueprint('pengguna', __name__)

def _get_session_user_id():
    """Mengambil ID User dari session dengan aman, mirip style warung_routes"""
    u = session.get("user") or {}
    return u.get("IdPengguna") or u.get("id") or None
    
# Profil
@pengguna_bp.route('/profil')
def profil():
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))

    id_pengguna = _get_session_user_id()
    if not id_pengguna:
        return redirect(url_for('auth.auth_page'))

    # Ambil data fresh dari database berdasarkan ID
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    pengguna = None
    try:
        cur.execute("SELECT * FROM Pengguna WHERE IdPengguna = %s", (id_pengguna,))
        data = cur.fetchone()
        if data:
            pengguna = Pengguna(
                idPengguna=data['IdPengguna'],
                nama=data['NamaPengguna'],
                email=data['Email'],
                password='', # Password tidak perlu ditampilkan
                peran=data['Peran'],
                nomor_telepon=data.get('nomorTeleponPengguna')
            )
    finally:
        cur.close()
        conn.close()

    if not pengguna:
        return redirect(url_for('auth.auth_page'))

    return render_template('profil.html', pengguna=pengguna)

@pengguna_bp.route("/editProfil", methods=['GET', 'POST'])
def editProfil():
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))

    id_pengguna = _get_session_user_id()
    if not id_pengguna:
        return redirect(url_for('auth.auth_page'))

    # --- LOGIC GET: TAMPILKAN FORM ---
    if request.method == 'GET':
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT * FROM Pengguna WHERE IdPengguna = %s", (id_pengguna,))
            data = cur.fetchone()
            
            if not data:
                return redirect(url_for('auth.auth_page'))

            # Buat objek pengguna dari data Database (Bukan Session)
            pengguna = Pengguna(
                idPengguna=data['IdPengguna'],
                nama=data['NamaPengguna'],
                email=data['Email'],
                password='', 
                peran=data['Peran'],
                nomor_telepon=data.get('nomorTeleponPengguna')
            )
            return render_template('editprofil.html', pengguna=pengguna)
        finally:
            cur.close()
            conn.close()

    # --- LOGIC POST: SIMPAN PERUBAHAN ---
    if request.method == 'POST':
        nama_baru = request.form.get('nama')
        email_baru = request.form.get('email')
        telp_baru = request.form.get('no_telp')

        # Siapkan objek untuk update
        pengguna = Pengguna(
            idPengguna=id_pengguna,
            nama=nama_baru,
            email=email_baru,
            password='', 
            peran=session['user'].get('Peran'), # Peran jarang berubah
            nomor_telepon=telp_baru
        )

        gambar_blob = None
        mime_type = None
        
        # Cek apakah ada file foto yang diupload
        if 'foto_profil' in request.files:
            file = request.files['foto_profil']
            if file.filename != '':
                gambar_blob = file.read()
                mime_type = file.mimetype

        # 1. Simpan ke Database
        # Menggunakan method update_profil yang sudah ada di model Anda
        pengguna.update_profil(gambar_blob, mime_type)

        # 2. Update Session (HANYA TEXT, JANGAN GAMBAR)
        # Kita update session agar nama di navbar berubah tanpa relogin
        if 'user' in session:
            session['user']['NamaPengguna'] = nama_baru
            session['user']['Email'] = email_baru
            session['user']['nomorTeleponPengguna'] = telp_baru
            
            # Pastikan kunci gambar DIBUANG dari session agar tidak error cookie full
            session['user'].pop('GambarPengguna', None)
            session['user'].pop('MimeGambarPengguna', None)
            
            session.modified = True

        return redirect(url_for('pengguna.profil'))


@pengguna_bp.route('/foto_profil/<int:id>')
def get_foto_profil(id):
    # Logic persis seperti warung_image di warung_routes
    # Ambil langsung dari DB, streaming binary ke browser
    gambar_blob, mime_type = Pengguna.ambil_foto_profil(id)
    
    if not gambar_blob:
        # Bisa return gambar default atau 404
        # Disini kita abort 404, nanti di HTML handle onerror
        abort(404)

    buf = BytesIO(gambar_blob)
    mime = mime_type or "application/octet-stream"
    
    resp = make_response(send_file(buf, mimetype=mime))
    resp.headers["Content-Length"] = str(len(gambar_blob))
    resp.headers["Cache-Control"] = "public, max-age=86400"

    return resp
# Menu
@pengguna_bp.route("/menu")
def menu():
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))

    user_data = session['user']
    pengguna = Pengguna(
        idPengguna=user_data['IdPengguna'],
        nama=user_data['NamaPengguna'],
        email=user_data['Email'],
        password='', 
        peran=user_data['Peran']
    )
    return render_template('menu.html', pengguna=pengguna)

@pengguna_bp.route("/penjual/menu")
def menu_penjual():
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))

    user_data = session['user']
    pengguna = Pengguna(
        idPengguna=user_data['IdPengguna'],
        nama=user_data['NamaPengguna'],
        email=user_data['Email'],
        password='', 
        peran=user_data['Peran']
    )

    return render_template('menuPenjual.html', pengguna=pengguna)
    
@pengguna_bp.route("/editAlamat")
def editAlamat():
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))

    id_pengguna = _get_session_user_id()
    
    # Ambil data lokasi user saat ini dari DB
    data = Pengguna.get_lokasi(id_pengguna) or {}
    
    return render_template('editAlamatPengguna.html', 
                           current_alamat=data.get('Alamat'),
                           current_patokan=data.get('Patokan'),
                           current_kordinat=data.get('Kordinat'))

@pengguna_bp.route("/simpan_alamat", methods=['POST'])
def simpan_alamat():
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Sesi habis'}), 401

    id_pengguna = _get_session_user_id()
    
    # Ambil data dari FormData Javascript
    kordinat = request.form.get('kordinat')
    alamat = request.form.get('alamat')
    patokan = request.form.get('patokan')

    if not kordinat:
        return jsonify({'status': 'error', 'message': 'Koordinat wajib diisi'}), 400
    try:
        # Panggil Model
        p = Pengguna(id_pengguna, "", "", "", "") # Dummy object
        p.update_lokasi(alamat, patokan, kordinat)

        # Update Session agar tidak perlu login ulang untuk melihat perubahan
        session['user']['Kordinat'] = kordinat
        session['user']['Alamat'] = alamat
        session['user']['Patokan'] = patokan
        session.modified = True

        return jsonify({'status': 'success'})
    except Exception as e:
        current_app.logger.error(f"Gagal simpan alamat: {e}")
        return jsonify({'status': 'error', 'message': 'Gagal menyimpan ke database'}), 500
        

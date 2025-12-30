from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify, flash
from models.Obrolan import Obrolan
from models.Warung import Warung
from models.Pengguna import Pengguna
from models.Pesanan import Pesanan
from .db import get_db_connection
import traceback
import time

obrolan_bp = Blueprint('obrolan', __name__)

# --- HELPER FUNCTIONS ---
def _get_user_id():
    return session.get('user', {}).get('IdPengguna')

def _get_warung_id():
    user_id = _get_user_id()
    if not user_id: return None
    if session.get('user', {}).get('IdWarung'):
        return session['user']['IdWarung']
    
    conn = get_db_connection()
    # Sudah benar menggunakan buffered=True dan LIMIT 1
    cur = conn.cursor(dictionary=True, buffered=True) 
    try:
        cur.execute("SELECT IdWarung FROM Warung WHERE IdPenjual = %s LIMIT 1", (user_id,))
        res = cur.fetchone()
        return res['IdWarung'] if res else None
    finally:
        cur.close()
        conn.close()

# =========================================================
# 1. TRIGGER ROOM
# =========================================================
@obrolan_bp.route('/chat/mulai/<int:id_warung>')
def mulai_chat_warung(id_warung):
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))
    
    user_id = _get_user_id()
    id_ruang = Obrolan.get_or_create_room(id_pengguna=user_id, id_warung=id_warung)
    
    # PERBAIKAN: Kirim 'target' (id_warung) agar room_chat tahu siapa lawannya jika chat masih kosong
    return redirect(url_for('obrolan.room_chat', id_ruang=id_ruang, target=id_warung))

@obrolan_bp.route('/chat/hubungi_pembeli/<int:id_pembeli>')
def mulai_chat_pembeli(id_pembeli):
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))
    
    user_id_sekarang = _get_user_id() # ID User (Penjual) yang sedang login

    conn = get_db_connection()
    # PENTING: Gunakan buffered=True untuk mencegah error "Unread result found"
    cur = conn.cursor(dictionary=True, buffered=True) 
    
    try:
        # === PERBAIKAN UTAMA DI SINI ===
        # Berdasarkan gambar tabel Warung Anda:
        # Kolom pemilik warung adalah 'IdPenjual' (bukan IdPemilik/IdPengguna)
        query = "SELECT IdWarung FROM Warung WHERE IdPenjual = %s"
        
        cur.execute(query, (user_id_sekarang,))
        row = cur.fetchone()

        my_warung_id = row['IdWarung']

        # Buat Room Chat (IdPengguna=Pembeli, IdWarung=WarungKita)
        id_ruang = Obrolan.get_or_create_room(id_pengguna=id_pembeli, id_warung=my_warung_id)
        
        # Redirect ke Room Chat
        # Target = id_pembeli (Supaya nama di header chat adalah nama pembeli)
        return redirect(url_for('obrolan.room_chat', id_ruang=id_ruang, target=id_pembeli))
    
    except Exception as e:
        print(f"Error starting chat: {e}")
        flash("Gagal membuka obrolan.", "danger")
        return redirect(url_for('pesanan.list_pesanan_penjual'))
        
    finally:
        cur.close()
        conn.close()
# =========================================================
# 2. INBOX
# =========================================================
@obrolan_bp.route('/chat/inbox')
def inbox():
    # 1. Cek Login
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))

    user = session.get('user')
    peran = user.get('Peran')
    user_id = user.get('IdPengguna')

    # 2. Buat Timestamp (Anti-Cache untuk gambar)
    ts = int(time.time())

    daftar_chat_final = []
    raw_data = []

    # 3. Ambil Data Mentah dari Database (Berdasarkan Peran)
    if peran == 'pembeli':
        # Pembeli mengambil daftar chat dengan Warung
        raw_data = Obrolan.ambil_inbox_pembeli(user_id)
        
    elif peran == 'penjual':
        # Penjual mengambil daftar chat dengan Pembeli
        warung_id = _get_warung_id() # Pastikan fungsi helper ini ada
        
        if not warung_id:
            flash("Anda belum memiliki warung.", "warning")
            return redirect(url_for('warung.pendaftaran_warung'))
            
        raw_data = Obrolan.ambil_inbox_penjual(warung_id)
        
    else:
        # Jika peran tidak jelas
        return redirect(url_for('home.home'))

    # 4. PROSES DATA (COOKING TIME!)
    # Kita ubah data mentah menjadi data siap saji untuk HTML
    if raw_data:
        for item in raw_data:
            # Copy item ke dictionary baru agar bisa dimodifikasi
            chat_item = dict(item) 
            
            # --- LOGIKA PEMBUATAN URL GAMBAR ---
            if peran == 'pembeli':
                # Jika user adalah PEMBELI, lawan bicaranya adalah WARUNG.
                # Maka ambil gambar warung menggunakan 'IdWarung'.
                # Endpoint: 'warung.warung_image' (sesuaikan jika beda)
                if 'IdWarung' in item:
                    chat_item['GambarTampil'] = url_for('warung.warung_image', id_warung=item['IdWarung'], v=ts)
                else:
                    chat_item['GambarTampil'] = None

            elif peran == 'penjual':
                # Jika user adalah PENJUAL, lawan bicaranya adalah USER/PEMBELI.
                # Maka ambil foto profil user menggunakan 'IdPengguna'.
                # Endpoint: 'pengguna.get_foto_profil' (sesuai log error Anda sebelumnya)
                if 'IdPengguna' in item:
                    chat_item['GambarTampil'] = url_for('pengguna.get_foto_profil', id=item['IdPengguna'], v=ts)
                else:
                    chat_item['GambarTampil'] = None

            # Masukkan item yang sudah ada URL gambarnya ke list final
            daftar_chat_final.append(chat_item)

    # 5. Kirim ke HTML
    # Karena kita pakai kunci 'GambarTampil', HTML Pembeli & Penjual jadi seragam.
    if peran == 'pembeli':
        return render_template('kontakPembeli.html', daftar_chat=daftar_chat_final)
    else:
        return render_template('kontakPenjual.html', daftar_chat=daftar_chat_final)

# =========================================================
# 3. ROOM CHAT
# =========================================================
@obrolan_bp.route('/chat/room/<id_ruang>')
def room_chat(id_ruang):
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))
    
    user_id = _get_user_id()
    peran = session['user'].get('Peran')
    
    # Ambil parameter 'target' dari URL (jika ada)
    target_param = request.args.get('target')

    history = Obrolan.get_chat_history(id_ruang)
    
    lawan_bicara = {}
    
    # --- LOGIKA PENENTUAN LAWAN BICARA ---
    # Skenario 1: Room Baru (History Kosong) -> Wajib pakai target_param
    if not history:
        if not target_param:
            flash("Chat tidak valid.", "error")
            return redirect(url_for('obrolan.inbox'))
            
        # Set ID lawan dari parameter URL
        id_lawan = int(target_param)
        
        if peran == 'pembeli':
            # Pembeli ngobrol sama Warung
            w = Warung().get_by_id(id_lawan)
            if w:
                lawan_bicara = {
                    'nama': w.get_nama_warung(),
                    # PERUBAHAN DI SINI: Key jadi 'GambarToko'
                    'GambarToko': url_for('warung.warung_profil_image', id_warung=w.get_id_warung()),
                    'id_target': w.get_id_warung(),
                    'tipe_target': 'warung'
                }
        else:
            # Penjual ngobrol sama Pembeli
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT NamaPengguna, IdPengguna FROM Pengguna WHERE IdPengguna=%s", (id_lawan,))
            p = cur.fetchone()
            cur.close()
            conn.close()
            if p:
                lawan_bicara = {
                    'nama': p['NamaPengguna'],
                    # PERUBAHAN DI SINI: Key jadi 'GambarToko'
                    'GambarToko': url_for('pengguna.get_foto_profil', id=p['IdPengguna']),
                    'id_target': p['IdPengguna'],
                    'tipe_target': 'pembeli'
                }

    # Skenario 2: Room Sudah Ada Chat (History Ada)
    else:
        # Ambil info dari pesan terakhir
        sample = history[0]
        
        if peran == 'pembeli':
            w = Warung().get_by_id(sample.id_warung)
            if w:
                lawan_bicara = {
                    'nama': w.get_nama_warung(),
                    # PERUBAHAN DI SINI: Key jadi 'GambarToko'
                    'GambarToko': url_for('warung.warung_profil_image', id_warung=w.get_id_warung()),
                    'id_target': w.get_id_warung(),
                    'tipe_target': 'warung'
                }
            
        elif peran == 'penjual':
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            # Asumsi: sample.id_pengguna adalah ID Pembeli
            cur.execute("SELECT NamaPengguna, IdPengguna FROM Pengguna WHERE IdPengguna=%s", (sample.id_pengguna,))
            p = cur.fetchone()
            cur.close()
            conn.close()
            
            if p:
                lawan_bicara = {
                    'nama': p['NamaPengguna'],
                    # PERUBAHAN DI SINI: Key jadi 'GambarToko'
                    'GambarToko': url_for('pengguna.get_foto_profil', id=p['IdPengguna']),
                    'id_target': p['IdPengguna'],
                    'tipe_target': 'pembeli'
                }

    return render_template('ruangObrolan.html', 
                           chats=history, 
                           id_ruang=id_ruang, 
                           lawan=lawan_bicara,
                           user_id=user_id)
# =========================================================
# 4. API (AJAX)
# =========================================================
@obrolan_bp.route('/chat/api/kirim', methods=['POST'])
def api_kirim_pesan():
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Anda harus login'}), 401

    # Ambil data (Handle FormData maupun JSON)
    data = request.form if request.form else request.json
    
    isi = data.get('isi')
    id_ruang = data.get('id_ruang')
    id_target = data.get('id_target') 
    
    # 1. Debugging: Cek data yang masuk di Terminal
    print(f"DEBUG CHAT: Isi={isi}, Ruang={id_ruang}, Target={id_target}")

    if not isi or not id_ruang or not id_target:
        return jsonify({'status': 'error', 'message': 'Data tidak lengkap (Target/Isi kosong)'}), 400

    try:
        user = session.get('user')
        user_id = user.get('IdPengguna')
        peran = user.get('Peran')

        chat = Obrolan()
        chat.isi = isi
        chat.id_ruang = id_ruang
        chat.status = 'sent'
        
        # 2. Konversi ID ke Integer (Penting untuk Database)
        # Seringkali error terjadi karena ID masih berupa String "5" bukan Int 5
        id_target_int = int(id_target)

        if peran == 'pembeli':
            chat.pengirim = 'pembeli'
            chat.id_pengguna = user_id
            chat.id_warung = id_target_int # Pastikan INT
        else:
            chat.pengirim = 'penjual'
            chat.id_warung = _get_warung_id()
            chat.id_pengguna = id_target_int # Pastikan INT

        # 3. Eksekusi Simpan
        chat.kirim()
        
        return jsonify({'status': 'success', 'data': chat.to_dict()})

    except Exception as e:
        # 4. Tangkap Error Spesifik
        traceback.print_exc() # Print error lengkap ke terminal server
        print(f"ERROR DB: {e}") 
        return jsonify({'status': 'error', 'message': str(e)}), 500
@obrolan_bp.route('/chat/api/history/<id_ruang>')
def api_get_history(id_ruang):
    try:
        chats = Obrolan.get_chat_history(id_ruang)
        data = [c.to_dict() for c in chats]
        return jsonify(data)
    except Exception as e:
        print(f"Error history: {e}")
        return jsonify([]), 200 
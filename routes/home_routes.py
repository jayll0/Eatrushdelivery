from flask import Blueprint, render_template, redirect, url_for, session, Response, abort, request
from models.Warung import Warung
from models.Makanan import Makanan
from .db import get_db_connection
import time

home_bp = Blueprint("home", __name__)

@home_bp.route('/home') # Sesuaikan dengan dekorator route Anda
def home():
    if 'user' not in session:
        return redirect(url_for('auth.auth_page'))
    
    user = session.get('user')
    q = request.args.get('q', '').strip()
    typ = request.args.get('type', 'all').strip()
    sort = request.args.get('sort', '').strip()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    offset = (page - 1) * per_page

    # 1. BUAT TIMESTAMP (ANTI-CACHE)
    ts = int(time.time())

    warung_list = []
    makanan_list = []

    # --- LOGIKA WARUNG ---
    if typ in ('all', 'warung'):
        if q:
            warungs = Warung().search_by_name(q, limit=per_page, offset=offset)
        else:
            sort_opt = None
            if sort == "highest":
                sort_opt = "highest"
            elif sort == "lowest":
                sort_opt = "lowest"
            warungs = Warung().get_all(limit=per_page, offset=offset, sort_by_rating=sort_opt)
        
        for w in warungs:
            # Cek apakah warung punya gambar
            has_img = getattr(w, "get_gambar_warung", lambda: None)()
            
            warung_list.append({
                'IdWarung': w.get_id_warung(),
                'IdPenjual': w.get_id_penjual(),
                'NamaWarung': w.get_nama_warung(),
                'AlamatWarung': w.get_alamat_warung(),
                'Rating': w.get_rating_warung(),
                # UPDATE DISINI: Tambahkan v=ts
                'GambarToko': url_for('home.warung_gambar', id_warung=w.get_id_warung(), v=ts) if has_img else None
            })

    # --- LOGIKA MAKANAN ---
    if typ in ('all', 'makanan'):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            params = []
            sql_base = """
                SELECT m.IdMakanan, m.IdWarung, m.NamaMakanan, m.HargaMakanan,
                       m.DetailMakanan, m.Stok, m.GambarMakanan, m.Rating,
                       COALESCE(s.total_sold,0) AS total_sold
                FROM Makanan m
                LEFT JOIN (
                    SELECT p.IdMakanan, SUM(p.BanyakPesanan) AS total_sold
                    FROM Pesanan p
                    GROUP BY p.IdMakanan
                ) s ON s.IdMakanan = m.IdMakanan
            """
            where_clauses = []
            if q:
                where_clauses.append("m.NamaMakanan LIKE %s")
                params.append(f"%{q}%")
            if where_clauses:
                sql_base += " WHERE " + " AND ".join(where_clauses)

            order_clause = " ORDER BY m.NamaMakanan ASC"
            if sort in ("highest", "lowest"):
                order_clause = (" ORDER BY m.Rating DESC, m.NamaMakanan ASC"
                                if sort == "highest"
                                else " ORDER BY m.Rating ASC, m.NamaMakanan ASC")
            elif sort in ("sold_high", "sold_low"):
                order_clause = (" ORDER BY total_sold DESC, m.NamaMakanan ASC"
                                if sort == "sold_high"
                                else " ORDER BY total_sold ASC, m.NamaMakanan ASC")

            sql = sql_base + order_clause + " LIMIT %s OFFSET %s"
            params.extend([per_page, offset])

            cur.execute(sql, tuple(params))
            rows = cur.fetchall() or []

            # fallback: if sorting by sold and no rows returned, try using Makanan.Terjual column
            if not rows and sort in ("sold_high", "sold_low"):
                try:
                    params2 = []
                    sql2 = """
                        SELECT m.IdMakanan, m.IdWarung, m.NamaMakanan, m.HargaMakanan,
                               m.DetailMakanan, m.Stok, m.GambarMakanan, m.Rating,
                               COALESCE(m.Terjual,0) AS total_sold
                        FROM Makanan m
                    """
                    if q:
                        sql2 += " WHERE m.NamaMakanan LIKE %s"
                        params2.append(f"%{q}%")
                    order2 = " ORDER BY total_sold DESC, m.NamaMakanan ASC" if sort == "sold_high" else " ORDER BY total_sold ASC, m.NamaMakanan ASC"
                    sql2 += order2 + " LIMIT %s OFFSET %s"
                    params2.extend([per_page, offset])
                    cur.execute(sql2, tuple(params2))
                    rows = cur.fetchall() or []
                except Exception:
                    rows = []
            
            for r in rows:
                makanan_list.append({
                    'IdMakanan': r.get('IdMakanan'),
                    'IdWarung': r.get('IdWarung'),
                    'NamaMakanan': r.get('NamaMakanan'),
                    'HargaMakanan': r.get('HargaMakanan'),
                    'DetailMakanan': r.get('DetailMakanan'),
                    'Stok': r.get('Stok'),
                    'Rating': r.get('Rating'),
                    'TotalSold': r.get('total_sold'),
                    # UPDATE DISINI: Tambahkan v=ts
                    'GambarMakanan': url_for('home.makanan_gambar', id_makanan=r.get('IdMakanan'), v=ts) if r.get('GambarMakanan') else None
                })
        finally:
            cur.close()
            conn.close()

    return render_template('home.html', user=user, warung_list=warung_list, makanan_list=makanan_list, query=q, type=typ, sort=sort, page=page)

@home_bp.route('/makanan/<int:id_makanan>/gambar')
def makanan_gambar(id_makanan):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT GambarMakanan, MimeGambarMakanan FROM Makanan WHERE IdMakanan=%s", (id_makanan,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row or not row.get('GambarMakanan'):
        abort(404)
    data = row['GambarMakanan']
    mime = row.get('MimeGambarMakanan') or 'image/png'
    headers = {'Cache-Control': 'public, max-age=86400'}
    return Response(data, mimetype=mime, headers=headers)

@home_bp.route('/warung/<int:id_warung>/gambar')
def warung_gambar(id_warung):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT GambarWarung, MimeGambarWarung FROM Warung WHERE IdWarung=%s", (id_warung,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row or not row.get('GambarWarung'):
        abort(404)
    data = row['GambarWarung']
    mime = row.get('MimeGambarWarung') or 'image/png'
    headers = {'Cache-Control': 'public, max-age=86400'}
    return Response(data, mimetype=mime, headers=headers)

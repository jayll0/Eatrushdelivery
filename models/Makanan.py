# models/Makanan.py
from .db import get_db_connection 
import base64
from io import BytesIO
from PIL import Image

def process_image_bytes(input_bytes: bytes, max_width=800, max_height=800, quality=80, target_format="WEBP"):
    """
    Resize (maintain aspect ratio) if larger than max, then encode to target_format.
    Returns (out_bytes, mime_type, out_size, width, height).
    """
    img = Image.open(BytesIO(input_bytes))
    img = img.convert("RGBA") if img.mode in ("LA", "RGBA", "P") else img.convert("RGB")

    orig_w, orig_h = img.size
    ratio = min(max_width / orig_w, max_height / orig_h, 1.0)
    if ratio < 1.0:
        new_w = int(orig_w * ratio)
        new_h = int(orig_h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    else:
        new_w, new_h = orig_w, orig_h

    out = BytesIO()
    fmt = target_format.upper()
    save_kwargs = {}
    if fmt in ("JPEG", "JPG"):
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
    elif fmt == "WEBP":
        save_kwargs["quality"] = quality
        save_kwargs["method"] = 6

    if fmt in ("JPEG", "JPG") and img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255,255,255))
        background.paste(img, mask=img.split()[3])
        img = background

    img.save(out, format=fmt, **save_kwargs)
    out_bytes = out.getvalue()
    mime = "image/webp" if fmt == "WEBP" else f"image/{fmt.lower()}"
    return out_bytes, mime, len(out_bytes), new_w, new_h


class Makanan:
    _id_makanan: int
    _nama_makanan: str
    _harga_makanan: float
    _deskripsi_makanan: str
    _rating_makanan: float
    _gambar_makanan: bytes
    _id_warung: int
    _stok_makanan: int

    def __init__(self,
                 id_makanan=None,
                 nama="",
                 harga=0.0,
                 deskripsi="",
                 rating=0.0,
                 gambar=None,
                 id_warung=None,
                 stok=0,
                 mime_gambar=None,
                 size_gambar=None):
        self._id_makanan = id_makanan
        self._nama_makanan = nama
        self._harga_makanan = harga
        self._deskripsi_makanan = deskripsi
        self._rating_makanan = rating
        self._gambar_makanan = gambar
        self._id_warung = id_warung
        self._stok_makanan = stok
        self._mime_gambar = mime_gambar
        self._size_gambar = size_gambar


    def get_stok_makanan(self):
        return self._stok_makanan

    def set_stok_makanan(self, new_stok):
        self._stok_makanan = new_stok

    def get_id_makanan(self):
        return self._id_makanan

    def set_id_makanan(self, new_id):
        self._id_makanan = new_id

    def get_nama_makanan(self):
        return self._nama_makanan

    def set_nama_makanan(self, new_nama):
        self._nama_makanan = new_nama

    def get_harga_makanan(self):
        return self._harga_makanan

    def set_harga_makanan(self, new_harga):
        self._harga_makanan = new_harga

    def get_deskripsi_makanan(self):
        return self._deskripsi_makanan

    def set_deskripsi_makanan(self, new_deskripsi):
        self._deskripsi_makanan = new_deskripsi

    def get_rating_makanan(self):
        return self._rating_makanan

    def set_rating_makanan(self, new_rating):
        self._rating_makanan = new_rating

    def get_gambar_makanan(self):
        return self._gambar_makanan

    def set_gambar_makanan(self, new_gambar):
        self._gambar_makanan = new_gambar

    def get_id_warung(self):
        return self._id_warung

    def set_id_warung(self, new_id_warung):
        self._id_warung = new_id_warung

    def get_mime_gambar(self):
        return self._mime_gambar

    def get_size_gambar(self):
        return self._size_gambar
    
    def get_all(self, only_available=True, limit=None, offset=None):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            sql = """
                SELECT IdMakanan, IdWarung, NamaMakanan, HargaMakanan, DetailMakanan,
                       Stok, GambarMakanan, Rating, MimeGambarMakanan, SizeGambarMakanan
                FROM Makanan
            """
            params = []
            if only_available:
                sql += " WHERE Tersedia=1"
            sql += " ORDER BY NamaMakanan ASC"
            if limit is not None:
                sql += " LIMIT %s"
                params.append(limit)
                if offset is not None:
                    sql += " OFFSET %s"
                    params.append(offset)

            cur.execute(sql, tuple(params) if params else None)
            rows = cur.fetchall()

            result = []
            for row in rows:
                result.append(Makanan(
                    id_makanan=row["IdMakanan"],
                    nama=row["NamaMakanan"],
                    harga=row["HargaMakanan"],
                    deskripsi=row["DetailMakanan"],
                    rating=row["Rating"],
                    gambar=row["GambarMakanan"],
                    id_warung=row["IdWarung"],
                    stok=row["Stok"],
                    mime_gambar=row["MimeGambarMakanan"],
                    size_gambar=row["SizeGambarMakanan"]
                ))
            return result
        finally:
            cur.close()
            conn.close()

    def get_by_id(self, id_makanan):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("""
                SELECT IdMakanan, IdWarung, NamaMakanan, HargaMakanan, DetailMakanan,
                       Stok, GambarMakanan, Rating, MimeGambarMakanan, SizeGambarMakanan
                FROM Makanan WHERE IdMakanan=%s
            """, (id_makanan,))
            row = cur.fetchone()
            if not row:
                return None

            return Makanan(
                id_makanan=row["IdMakanan"],
                nama=row["NamaMakanan"],
                harga=row["HargaMakanan"],
                deskripsi=row["DetailMakanan"],
                rating=row["Rating"],
                gambar=row["GambarMakanan"],
                id_warung=row["IdWarung"],
                stok=row["Stok"],
                mime_gambar=row["MimeGambarMakanan"],
                size_gambar=row["SizeGambarMakanan"]
            )
        finally:
            cur.close()
            conn.close()

    def get_by_warung(self, id_warung, limit=None, offset=None):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            sql = """
                SELECT IdMakanan, IdWarung, NamaMakanan, HargaMakanan, DetailMakanan,
                       Stok, GambarMakanan, Rating, MimeGambarMakanan, SizeGambarMakanan
                FROM Makanan
                WHERE IdWarung=%s
                ORDER BY NamaMakanan ASC
            """
            params = [id_warung]
            if limit is not None:
                sql += " LIMIT %s"
                params.append(limit)
                if offset is not None:
                    sql += " OFFSET %s"
                    params.append(offset)

            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

            result = []
            for row in rows:
                result.append(Makanan(
                    id_makanan=row["IdMakanan"],
                    nama=row["NamaMakanan"],
                    harga=row["HargaMakanan"],
                    deskripsi=row["DetailMakanan"],
                    rating=row["Rating"],
                    gambar=row["GambarMakanan"],
                    id_warung=row["IdWarung"],
                    stok=row["Stok"],
                    mime_gambar=row["MimeGambarMakanan"],
                    size_gambar=row["SizeGambarMakanan"]
                ))
            return result
        finally:
            cur.close()
            conn.close()

    # -------------------------
    # INSERT & UPDATE
    # -------------------------
    def save_new(self):
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO Makanan
                (IdWarung, NamaMakanan, DetailMakanan, HargaMakanan, GambarMakanan,
                 MimeGambarMakanan, SizeGambarMakanan, Stok, Tersedia)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1)
            """, (
                self._id_warung,
                self._nama_makanan,
                self._deskripsi_makanan,
                self._harga_makanan,
                self._gambar_makanan,
                self._mime_gambar,
                self._size_gambar,
                self._stok_makanan
            ))
            conn.commit()
            self._id_makanan = cur.lastrowid
            return self._id_makanan
        finally:
            cur.close()
            conn.close()

    def save_update(self):
        if not self._id_makanan:
            raise ValueError("Id makanan tidak diset.")

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE Makanan SET
                    NamaMakanan=%s,
                    HargaMakanan=%s,
                    DetailMakanan=%s,
                    Stok=%s,
                    GambarMakanan=%s,
                    MimeGambarMakanan=%s,
                    SizeGambarMakanan=%s
                WHERE IdMakanan=%s
            """,
            (
                self._nama_makanan,
                self._harga_makanan,
                self._deskripsi_makanan,
                self._stok_makanan,
                self._gambar_makanan,
                self._mime_gambar,
                self._size_gambar,
                self._id_makanan
            ))
            conn.commit()
            return cur.rowcount
        finally:
            cur.close()
            conn.close()

    # -------------------------
    # DELETE
    # -------------------------
    def delete(self):
        if not self._id_makanan:
            raise ValueError("Id makanan tidak diset.")
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM Makanan WHERE IdMakanan=%s", (self._id_makanan,))
            conn.commit()
            return cur.rowcount
        finally:
            cur.close()
            conn.close()

    # -------------------------
    # IMAGE HANDLING
    # -------------------------
    def set_gambar_from_upload(self, file_bytes, save_to_db=True, max_w=800, max_h=800, quality=80, fmt="WEBP"):
        out_bytes, mime, size, w, h = process_image_bytes(
            file_bytes, max_width=max_w, max_height=max_h, quality=quality, target_format=fmt
        )

        self._gambar_makanan = out_bytes
        self._mime_gambar = mime
        self._size_gambar = size

        if save_to_db:
            if not self._id_makanan:
                raise ValueError("IdMakanan belum ada. Gunakan save_new() dulu.")

            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("""
                    UPDATE Makanan
                    SET GambarMakanan=%s, MimeGambarMakanan=%s, SizeGambarMakanan=%s
                    WHERE IdMakanan=%s
                """, (out_bytes, mime, size, self._id_makanan))
                conn.commit()
            finally:
                cur.close()
                conn.close()

        return mime, size, w, h

    def delete_gambar(self):
        if not self._id_makanan:
            raise ValueError("Id makanan tidak diset.")
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE Makanan
                SET GambarMakanan=NULL, MimeGambarMakanan=NULL, SizeGambarMakanan=NULL
                WHERE IdMakanan=%s
            """, (self._id_makanan,))
            conn.commit()
            self._gambar_makanan = None
            self._mime_gambar = None
            self._size_gambar = None
            return cur.rowcount
        finally:
            cur.close()
            conn.close()

    def gambar_data_uri(self):
        if not self._gambar_makanan:
            return None
        try:
            mime = self._mime_gambar or "image/webp"
            b64 = base64.b64encode(self._gambar_makanan).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except:
            return None

    # -------------------------
    # RATING
    # -------------------------
    def hitung_rating_baru(self, nilai_baru):
        try:
            nilai_baru = float(nilai_baru)
        except:
            return None

        current = float(self._rating_makanan or 0)
        self._rating_makanan = (current + nilai_baru) / 2.0

        if not self._id_makanan:
            raise ValueError("Id makanan belum ada.")

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("UPDATE Makanan SET Rating=%s WHERE IdMakanan=%s",
                        (self._rating_makanan, self._id_makanan))
            conn.commit()
            return self._rating_makanan
        finally:
            cur.close()
            conn.close()
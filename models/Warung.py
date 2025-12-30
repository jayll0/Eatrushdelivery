from .db import get_db_connection
import base64

class Warung:
    _id_warung: int
    _id_penjual: int
    _nama_warung: str
    _alamat_warung: str
    _nomor_telepon_warung: str
    _gambar_warung: bytes
    _rating_warung: float
    _makanan: list

    def __init__(
        self,
        id_warung=None,
        id_penjual=0,
        nama_warung="",
        alamat_warung="",
        nomor_telepon_warung="",
        gambar_warung=None,
        rating_warung=0.0,
        kordinat_warung=None,
        mime_gambar=None,
        jam_buka=None,
        jam_tutup=None,
        size_gambar=None
    ):
        self._id_warung = id_warung
        self._id_penjual = id_penjual
        self._nama_warung = nama_warung
        self._alamat_warung = alamat_warung
        self._nomor_telepon_warung = nomor_telepon_warung
        self._gambar_warung = gambar_warung
        self._rating_warung = float(rating_warung or 0.0)
        self._kordinat_warung = kordinat_warung
        self._mime_gambar = mime_gambar
        self._size_gambar = size_gambar
    
        self._jam_buka = jam_buka
        self._jam_tutup = jam_tutup
    
        self._makanan = []

    def get_id_warung(self):
        return self._id_warung

    def set_id_warung(self, new_id):
        self._id_warung = new_id

    def get_id_penjual(self):
        return self._id_penjual

    def set_id_penjual(self, new_id):
        self._id_penjual = new_id

    def get_nama_warung(self):
        return self._nama_warung

    def set_nama_warung(self, new_nama):
        self._nama_warung = new_nama

    def get_alamat_warung(self):
        return self._alamat_warung

    def set_alamat_warung(self, new_alamat):
        self._alamat_warung = new_alamat

    def get_nomor_telepon_warung(self):
        return self._nomor_telepon_warung

    def set_nomor_telepon_warung(self, new_nomor):
        self._nomor_telepon_warung = new_nomor

    def get_gambar_warung(self):
        return self._gambar_warung

    def get_mime_gambar(self):
        return getattr(self, "_mime_gambar", None)

    def get_size_gambar(self):
        return getattr(self, "_size_gambar", None)

    def set_gambar_warung(self, new_gambar):
        self._gambar_warung = new_gambar

    def get_rating_warung(self):
        return self._rating_warung

    def set_rating_warung(self):
        """
        Hitung rating warung berdasarkan rating semua makanan milik warung.
        Algoritma: rata-rata sederhana dari kolom Rating di tabel Makanan
        (mengabaikan NULL atau 0 jika tidak ingin dihitung — di sini kita ambil
        hanya nilai > 0 supaya makanan belum dinilai tidak mempengaruhi).
        Setelah dihitung, simpan ke DB di kolom Rating dan set ke instance.
        Kembalikan nilai rating baru (float).
        """
        if self._id_warung is None:
            raise ValueError("Id Warung belum diset.")

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            # rata-rata hanya dari makanan yang punya rating > 0
            cur.execute("""
                SELECT AVG(CAST(Rating AS DECIMAL(10,4))) as avg_rating
                FROM Makanan
                WHERE IdWarung=%s AND Rating IS NOT NULL AND Rating > 0
            """, (self._id_warung,))
            row = cur.fetchone()
            avg = None
            if row:
                # cursor default tidak dictionary; row[0] -> avg_rating
                avg = row[0] if isinstance(row, tuple) else row.get("avg_rating")

            # jika tidak ada rating (None) set 0.0
            new_rating = float(avg) if avg is not None else 0.0

            # update ke tabel Warung
            cur.execute("UPDATE Warung SET Rating=%s WHERE IdWarung=%s", (new_rating, self._id_warung))
            conn.commit()

            # set ke instance
            self._rating_warung = new_rating
            return new_rating
        finally:
            cur.close()
            conn.close()

    def get_kordinat_warung(self):
        return self._kordinat_warung

    def set_kordinat_warung(self, new_kordinat):
        self._kordinat_warung = new_kordinat

    def get_makanan(self):
        return self._makanan

    def tambah_makanan(self, makanan_obj):
        self._makanan.append(makanan_obj)

    def save_new(self):
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO Warung
                (IdPenjual, NamaWarung, AlamatWarung, NomorTeleponWarung, GambarWarung, Rating, KordinatWarung, MimeGambarWarung, SizeGambarWarung, DibuatPada)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
            """, (
                self._id_penjual,
                self._nama_warung,
                self._alamat_warung,
                self._nomor_telepon_warung,
                self._gambar_warung,
                self._rating_warung,
                self._kordinat_warung,
                self._mime_gambar,
                self._size_gambar
            ))
            conn.commit()
            try:
                self._id_warung = cur.lastrowid
            except:
                pass
            return self._id_warung
        finally:
            cur.close()
            conn.close()

    def save_update(self):
        if self._id_warung is None:
            raise ValueError("Id Warung belum diset")
    
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE Warung SET
                    IdPenjual=%s,
                    NamaWarung=%s,
                    AlamatWarung=%s,
                    NomorTeleponWarung=%s,
                    GambarWarung=%s,
                    Rating=%s,
                    KordinatWarung=%s,
                    MimeGambarWarung=%s,
                    SizeGambarWarung=%s
                WHERE IdWarung=%s
            """, (
                self._id_penjual,
                self._nama_warung,
                self._alamat_warung,
                self._nomor_telepon_warung,
                self._gambar_warung,
                self._rating_warung,
                self._kordinat_warung,
                self._mime_gambar,
                self._size_gambar,
                self._id_warung
            ))
            conn.commit()
            return cur.rowcount
        finally:
            cur.close()
            conn.close()


    def delete(self):
        if self._id_warung is None:
            raise ValueError("Id Warung belum diset")
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM Warung WHERE IdWarung=%s", (self._id_warung,))
            conn.commit()
            return cur.rowcount
        finally:
            cur.close()
            conn.close()

    # -------------------------
    # Finders (with optional pagination)
    # -------------------------
    def get_all(self, limit=None, offset=None, sort_by_rating=None):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            sql = """SELECT IdWarung, IdPenjual, NamaWarung, AlamatWarung,
                            NomorTeleponWarung, GambarWarung, Rating, KordinatWarung,
                            MimeGambarWarung, SizeGambarWarung
                    FROM Warung"""
            if sort_by_rating == "highest":
                sql += " ORDER BY Rating DESC, NamaWarung ASC"
            elif sort_by_rating == "lowest":
                sql += " ORDER BY Rating ASC, NamaWarung ASC"
            else:
                sql += " ORDER BY NamaWarung ASC"

            params = []
            if limit is not None:
                sql += " LIMIT %s"
                params.append(limit)
                if offset is not None:
                    sql += " OFFSET %s"
                    params.append(offset)

            if params:
                cur.execute(sql, tuple(params))
            else:
                cur.execute(sql)

            rows = cur.fetchall()
            result = []
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
                    size_gambar=row.get("SizeGambarWarung")
                )
                result.append(w)
            return result
        finally:
            cur.close()
            conn.close()



    def get_by_id(self, id_warung):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("""
                SELECT IdWarung, IdPenjual, NamaWarung, AlamatWarung,
                       NomorTeleponWarung, GambarWarung, Rating, KordinatWarung,
                       MimeGambarWarung, SizeGambarWarung
                FROM Warung
                WHERE IdWarung=%s
            """, (id_warung,))
            row = cur.fetchone()
            if not row:
                return None
            return Warung(
                id_warung=row.get("IdWarung"),
                id_penjual=row.get("IdPenjual"),
                nama_warung=row.get("NamaWarung"),
                alamat_warung=row.get("AlamatWarung"),
                nomor_telepon_warung=row.get("NomorTeleponWarung"),
                gambar_warung=row.get("GambarWarung"),
                rating_warung=row.get("Rating") or 0.0,
                kordinat_warung=row.get("KordinatWarung"),
                mime_gambar=row.get("MimeGambarWarung"),
                size_gambar=row.get("SizeGambarWarung")
            )
        finally:
            cur.close()
            conn.close()

    def update_lokasi(self, kordinat, alamat=None):
        if self._id_warung is None:
            raise ValueError("Id Warung belum diset")
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            if alamat is None:
                cur.execute("UPDATE Warung SET KordinatWarung=%s WHERE IdWarung=%s", (kordinat, self._id_warung))
            else:
                cur.execute("UPDATE Warung SET KordinatWarung=%s, AlamatWarung=%s WHERE IdWarung=%s", (kordinat, alamat, self._id_warung))
                self._alamat_warung = alamat
            conn.commit()
            self._kordinat_warung = kordinat
            return cur.rowcount
        finally:
            cur.close()
            conn.close()

    def set_gambar_from_upload(self, file_bytes, save_to_db=True):
        """
        Versi sederhana: langsung simpan bytes tanpa library processing tambahan.
        """
        self._gambar_warung = file_bytes
        self._size_gambar = len(file_bytes)
        # Default mime type (bisa dikembangkan deteksinya jika perlu)
        self._mime_gambar = "image/jpeg" 

        if save_to_db:
            if self._id_warung is None:
                raise ValueError("Id Warung belum diset. Simpan warung dulu sebelum upload gambar.")
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("""
                    UPDATE Warung
                    SET GambarWarung=%s, MimeGambarWarung=%s, SizeGambarWarung=%s
                    WHERE IdWarung=%s
                """, (self._gambar_warung, self._mime_gambar, self._size_gambar, self._id_warung))
                conn.commit()
            finally:
                cur.close()
                conn.close()

    def get_gambar_data_uri(self):
        if not self._gambar_warung:
            return None
        try:
            mime = self._mime_gambar or "image/jpeg"
            b64 = base64.b64encode(self._gambar_warung).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except:
            return None

    def delete_makanan(self, id_makanan):
        # Import di dalam method untuk hindari Circular Import
        from models.Makanan import Makanan 
        
        if self._id_warung is None:
            raise ValueError("Id Warung belum diset.")
        
        m = Makanan().get_by_id(id_makanan)
        if not m:
            return 0
        if m.get_id_warung() != self._id_warung:
            raise PermissionError("Makanan bukan milik warung ini.")
        
        return m.delete()

    @staticmethod
    def ambil_foto_warung(id_warung):
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            # FIX: Menggunakan id_warung bukan id_pengguna
            query = "SELECT GambarWarung, MimeGambarWarung FROM Warung WHERE IdWarung = %s"
            cur.execute(query, (id_warung,))
            data = cur.fetchone()
            if data:
                return data[0], data[1]
            return None, None
        finally:
            cur.close()
            conn.close()
    
    def search_by_name(self, keyword, limit=20, offset=0):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            sql = "SELECT * FROM Warung WHERE NamaWarung LIKE %s LIMIT %s OFFSET %s"
            search_pattern = f"%{keyword}%"
            val = (search_pattern, limit, offset)
            
            cur.execute(sql, val)
            rows = cur.fetchall()
            
            results = []
            for row in rows:
                # PERBAIKAN DI SINI:
                # Gunakan constructor (parameter) agar internal variable terisi
                # sehingga w.get_id_warung() nanti tidak return None.
                w = Warung(
                    id_warung=row.get('IdWarung'),
                    id_penjual=row.get('IdPenjual'),
                    nama_warung=row.get('NamaWarung'),
                    alamat_warung=row.get('AlamatWarung'),
                    rating_warung=row.get('Rating'),
                    gambar_warung=row.get('GambarWarung'), 
                    # Jika ada kolom lain seperti kordinat, tambahkan juga:
                    kordinat_warung=row.get('KordinatWarung') 
                )
                
                # Jika Anda punya logika manual untuk atribut publik, bisa dihapus 
                # karena sudah ditangani class Warung via init di atas.
                
                results.append(w)
                
            return results
            
        except Exception as e:
            print(f"Error search_by_name: {e}")
            return []
        finally:
            if cur: cur.close()
            if conn: conn.close()
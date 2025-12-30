from .db import get_db_connection

class Pengguna:
    def __init__(self, idPengguna: int, nama: str, email: str, password: str, peran: str, nomor_telepon: str = None, kordinat: str = None, patokan: str = None):
        self.IdPengguna = idPengguna
        self.NamaPengguna = nama
        self.Email = email
        self.Password = password
        self.Peran = peran
        self.NomorTelepon = nomor_telepon
        self.Kordinat = kordinat
        self.Patokan = patokan

    def save(self) -> None:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO Pengguna (IdPengguna, NamaPengguna, Email, Password, Peran, nomorTeleponPengguna) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (self.IdPengguna, self.NamaPengguna, self.Email, self.Password, self.Peran, self.NomorTelepon)
        )
        conn.commit()
        cur.close()
        conn.close()

    def update(self) -> None:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE Pengguna SET NamaPengguna=%s, Email=%s, Password=%s, Peran=%s, nomorTeleponPengguna=%s WHERE IdPengguna=%s",
            (self.NamaPengguna, self.Email, self.Password, self.Peran, self.NomorTelepon, self.IdPengguna)
        )
        conn.commit()
        cur.close()
        conn.close()

    def update_profil(self, gambar_blob=None, mime_type=None) -> None:
        conn = get_db_connection()
        cur = conn.cursor()

        if gambar_blob:
            query = """
                UPDATE Pengguna 
                SET NamaPengguna=%s, Email=%s, nomorTeleponPengguna=%s, 
                    GambarPengguna=%s, MimeGambarPengguna=%s 
                WHERE IdPengguna=%s
            """
            cur.execute(query, (self.NamaPengguna, self.Email, self.NomorTelepon, gambar_blob, mime_type, self.IdPengguna))
        else:
            query = """
                UPDATE Pengguna 
                SET NamaPengguna=%s, Email=%s, nomorTeleponPengguna=%s 
                WHERE IdPengguna=%s
            """
            cur.execute(query, (self.NamaPengguna, self.Email, self.NomorTelepon, self.IdPengguna))

        conn.commit()
        cur.close()
        conn.close()

    def delete(self) -> None:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM Pengguna WHERE IdPengguna=%s", (self.IdPengguna,))
        conn.commit()
        cur.close()
        conn.close()
        
    def update_alamat(self, kordinat: str, patokan: str) -> None:
        conn = get_db_connection()
        cur = conn.cursor()
        
        query = "UPDATE Pengguna SET Kordinat = %s, Patokan = %s WHERE IdPengguna = %s"
        cur.execute(query, (kordinat, patokan, self.IdPengguna))
        
        conn.commit()
        cur.close()
        conn.close()

        # Update atribut di object saat ini juga agar sinkron
        self.Kordinat = kordinat
        self.Patokan = patokan
        
    # --- METHOD BARU (STATIC) ---
    # Kita pakai staticmethod agar bisa dipanggil tanpa perlu membuat objek Pengguna(...) dulu
    @staticmethod
    def ambil_foto_profil(id_pengguna):
        conn = get_db_connection()
        cur = conn.cursor()
        
        query = "SELECT GambarPengguna, MimeGambarPengguna FROM Pengguna WHERE IdPengguna = %s"
        cur.execute(query, (id_pengguna,))
        data = cur.fetchone()
        
        cur.close()
        conn.close()
        
        # Mengembalikan tuple (gambar, mime) atau (None, None) jika tidak ada
        if data:
            return data[0], data[1]
        return None, None
        
    def update_lokasi(self, alamat, patokan, kordinat) -> None:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            # Query update lengkap
            query = """
                UPDATE Pengguna 
                SET Alamat=%s, Patokan=%s, Kordinat=%s 
                WHERE IdPengguna=%s
            """
            cur.execute(query, (alamat, patokan, kordinat, self.IdPengguna))
            conn.commit()
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def get_lokasi(id_pengguna):
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT Alamat, Patokan, Kordinat FROM Pengguna WHERE IdPengguna=%s", (id_pengguna,))
            return cur.fetchone()
        finally:
            cur.close()
            conn.close()
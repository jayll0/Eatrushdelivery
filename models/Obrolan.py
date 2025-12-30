from dataclasses import dataclass, field
from datetime import datetime
import uuid
from typing import List, Optional, Dict, Any
from .db import get_db_connection

@dataclass
class Obrolan:
    id_obrolan: str = field(default_factory=lambda: str(uuid.uuid4()))
    id_pengguna: int = 0
    id_warung: int = 0
    isi: str = ""
    pengirim: str = "pembeli"  # 'pembeli' atau 'penjual'
    id_ruang: str = ""         
    status: str = "sent"
    waktu: str = field(default_factory=lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    reply_to_pesanan: Optional[int] = None

    # ==========================================
    # 1. CORE METHODS (Kirim & Room)
    # ==========================================

    @staticmethod
    def get_or_create_room(id_pengguna: int, id_warung: int) -> str:
        """Cek atau buat Room ID baru"""
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            query = "SELECT IdRuang FROM Obrolan WHERE IdPengguna = %s AND IdWarung = %s LIMIT 1"
            cur.execute(query, (id_pengguna, id_warung))
            result = cur.fetchone()
            if result:
                return result[0] if isinstance(result, tuple) else result['IdRuang']
            return str(uuid.uuid4())
        finally:
            cur.close()
            conn.close()

    def kirim(self) -> str:
        """Menyimpan pesan baru ke database"""
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            if not self.id_ruang:
                self.id_ruang = Obrolan.get_or_create_room(self.id_pengguna, self.id_warung)

            query = """
                INSERT INTO Obrolan 
                (IdObrolan, IdPengguna, IdWarung, Isi, Pengirim, IdRuang, ReplyToPesananWarung, Waktu, Status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cur.execute(query, (
                self.id_obrolan, self.id_pengguna, self.id_warung, 
                self.isi, self.pengirim, self.id_ruang, 
                self.reply_to_pesanan, self.waktu, self.status
            ))
            conn.commit()
            return self.id_obrolan
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def get_chat_history(id_ruang: str) -> List['Obrolan']:
        """Mengambil semua chat dalam satu room"""
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT * FROM Obrolan WHERE IdRuang = %s ORDER BY Waktu ASC", (id_ruang,))
            rows = cur.fetchall()
            results = []
            for row in rows:
                # Konversi waktu ke string jika tipe datanya datetime
                waktu_str = row['Waktu'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(row['Waktu'], 'strftime') else str(row['Waktu'])
                
                chat = Obrolan(
                    id_obrolan=row['IdObrolan'],
                    id_pengguna=row['IdPengguna'],
                    id_warung=row['IdWarung'],
                    isi=row['Isi'],
                    pengirim=row['Pengirim'],
                    id_ruang=row['IdRuang'],
                    status=row['Status'],
                    waktu=waktu_str,
                    reply_to_pesanan=row['ReplyToPesananWarung']
                )
                results.append(chat)
            return results
        finally:
            cur.close()
            conn.close()

    # ==========================================
    # 2. CRUD TAMBAHAN (Update & Delete)
    # ==========================================

    def update(self) -> None:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE Obrolan SET Isi=%s, Waktu=%s WHERE IdObrolan=%s",
                (self.isi, self.waktu, self.id_obrolan)
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def delete(self) -> None:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM Obrolan WHERE IdObrolan=%s", (self.id_obrolan,))
            conn.commit()
        finally:
            cur.close()
            conn.close()

    # ==========================================
    # 3. HELPER (to_dict)
    # ==========================================
    
    def to_dict(self) -> Dict[str, Any]:
        """Konversi objek ke dictionary untuk API/JSON"""
        # Parsing waktu agar formatnya rapi (Jam:Menit)
        waktu_val = self.waktu
        if isinstance(waktu_val, str):
            try:
                dt = datetime.strptime(waktu_val, '%Y-%m-%d %H:%M:%S')
                waktu_display = dt.strftime("%H:%M")
            except:
                waktu_display = waktu_val
        elif isinstance(waktu_val, datetime):
            waktu_display = waktu_val.strftime("%H:%M")
        else:
            waktu_display = str(waktu_val)

        return {
            "IdObrolan": self.id_obrolan,
            "IdPengguna": self.id_pengguna,
            "IdWarung": self.id_warung,
            "Isi": self.isi,
            "Waktu": waktu_display,
            "Pengirim": self.pengirim,
            "IdRuang": self.id_ruang
        }

    # ==========================================
    # 4. INBOX (Daftar Chat)
    # ==========================================

    @staticmethod
    def ambil_inbox_pembeli(id_pengguna: int) -> List[Dict]:
        """Mengambil daftar Warung yang pernah chat dengan Pembeli ini"""
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            # Query complex untuk mengambil pesan TERAKHIR dari setiap warung
            query = """
                SELECT W.IdWarung, W.NamaWarung, W.GambarWarung, 
                       O.IdRuang, O.Isi AS PesanTerakhir, O.Waktu
                FROM Obrolan O
                JOIN Warung W ON O.IdWarung = W.IdWarung
                WHERE O.IdPengguna = %s
                AND O.Waktu = (
                    SELECT MAX(Waktu) FROM Obrolan 
                    WHERE IdPengguna = O.IdPengguna AND IdWarung = O.IdWarung
                )
                ORDER BY O.Waktu DESC
            """
            cur.execute(query, (id_pengguna,))
            return cur.fetchall() or []
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def ambil_inbox_penjual(id_warung: int) -> List[Dict]:
        """Mengambil daftar Pembeli yang pernah chat dengan Warung ini"""
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            query = """
                SELECT P.IdPengguna, P.NamaPengguna, P.GambarPengguna,
                       O.IdRuang, O.Isi AS PesanTerakhir, O.Waktu
                FROM Obrolan O
                JOIN Pengguna P ON O.IdPengguna = P.IdPengguna
                WHERE O.IdWarung = %s
                AND O.Waktu = (
                    SELECT MAX(Waktu) FROM Obrolan 
                    WHERE IdWarung = O.IdWarung AND IdPengguna = O.IdPengguna
                )
                ORDER BY O.Waktu DESC
            """
            cur.execute(query, (id_warung,))
            return cur.fetchall() or []
        finally:
            cur.close()
            conn.close()
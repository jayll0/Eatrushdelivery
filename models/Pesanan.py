from dataclasses import dataclass, field, asdict
from typing import List, Dict, Set, Any, Optional
from datetime import datetime
from flask import current_app
from .db import get_db_connection
from models.Warung import Warung

@dataclass
class Pesanan:
    id_pesanan: int = 0
    id_pembeli: int = 0
    id_warung: int = 0
    total_harga: float = 0.0
    status: str = "Pembayaran"
    catatan: str = ""
    waktu_dibuat: str = field(default_factory=lambda: datetime.now().isoformat())
    details: List[Dict] = field(default_factory=list)
    warung: Optional[Warung] = None 

    def to_dict(self) -> Dict:
        return asdict(self)

    def add_detail(self, id_makanan: int, qty: int = 1, harga_satuan: float = 0.0, note: str = ""):
        if qty <= 0:
            raise ValueError("qty harus > 0")
        self.details.append({
            "id_makanan": int(id_makanan),
            "qty": int(qty),
            "harga_satuan": float(harga_satuan),
            "note": note or ""
        })

    def clear_details(self):
        self.details = []

    def create_with_items(self, items: List[Dict], id_pembeli: int, id_warung: int, catatan: str = "") -> int:
        if not items:
            raise ValueError("Tidak ada item untuk dipesan")
        
        MAX_ITEMS = int(current_app.config.get("MAX_ORDER_ITEMS", 200))
        if len(items) > MAX_ITEMS:
            raise ValueError(f"Jumlah item melebihi batas ({MAX_ITEMS})")

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            conn.start_transaction()

            ids_set = {int(i["id_makanan"]) for i in items}
            ids = tuple(ids_set)
            if not ids:
                raise ValueError("Item tidak valid")

            placeholders = ",".join(["%s"] * len(ids))
            q = f"SELECT IdMakanan, HargaMakanan, Stok, IdWarung FROM Makanan WHERE IdMakanan IN ({placeholders}) FOR UPDATE"
            cur.execute(q, ids)
            rows = {r["IdMakanan"]: r for r in cur.fetchall()}

            for it in items:
                mid = int(it["id_makanan"])
                qty = int(it.get("qty", 1))
                
                if mid not in rows:
                    raise ValueError(f"Makanan dengan id {mid} tidak ditemukan")
                
                stok = int(rows[mid].get("Stok") or 0)
                if stok < qty:
                    raise ValueError(f"Stok tidak cukup untuk IdMakanan={mid}")
                
                makanan_warung = rows[mid].get("IdWarung")
                if int(makanan_warung) != int(id_warung):
                    raise ValueError(f"Item IdMakanan={mid} bukan milik warung {id_warung}")

            total = 0.0
            for it in items:
                mid = int(it["id_makanan"])
                qty = int(it.get("qty", 1))
                harga = float(rows[mid]["HargaMakanan"] or 0.0)
                total += harga * qty

            status = self.status or "Pembayaran"
            insert_pw = """
                INSERT INTO PesananWarung (IdPembeli, IdWarung, TotalHarga, DeskripsiPesanan, Status, DibuatPada)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            now = datetime.now()
            cur.execute(insert_pw, (int(id_pembeli), int(id_warung), float(round(total,2)), catatan or None, status, now))
            id_pesanan_warung = cur.lastrowid
            
            if not id_pesanan_warung:
                raise RuntimeError("Gagal membuat pesanan")

            insert_detail = """
                INSERT INTO Pesanan (IdPesananWarung, IdMakanan, BanyakPesanan, Subtotal)
                VALUES (%s, %s, %s, %s)
            """
            update_makanan = "UPDATE Makanan SET Stok = GREATEST(COALESCE(Stok,0) - %s, 0) WHERE IdMakanan=%s"

            for it in items:
                mid = int(it["id_makanan"])
                qty = int(it.get("qty", 1))
                harga = float(rows[mid]["HargaMakanan"] or 0.0)
                subtotal = round(harga * qty, 2)
                
                cur.execute(insert_detail, (id_pesanan_warung, mid, qty, subtotal))
                cur.execute(update_makanan, (qty, mid))

            conn.commit()

            self.id_pesanan = int(id_pesanan_warung)
            self.id_pembeli = int(id_pembeli)
            self.id_warung = int(id_warung)
            self.total_harga = float(round(total,2))
            self.catatan = catatan or ""
            self.waktu_dibuat = datetime.now().isoformat()
            self.status = status
            self.details = items

            return int(id_pesanan_warung)
        
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            cur.close()
            conn.close()

    def save(self) -> int:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            if self.id_pesanan and self.id_pesanan > 0:
                cur.execute(
                    "UPDATE PesananWarung SET TotalHarga=%s, DeskripsiPesanan=%s, Status=%s WHERE IdPesananWarung=%s",
                    (self.total_harga, self.catatan, self.status, self.id_pesanan)
                )
                res = self.id_pesanan
            else:
                cur.execute(
                    "INSERT INTO PesananWarung (IdPembeli, IdWarung, TotalHarga, DeskripsiPesanan, Status, DibuatPada) VALUES (%s,%s,%s,%s,%s,%s)",
                    (self.id_pembeli, self.id_warung, self.total_harga, self.catatan, self.status, datetime.now())
                )
                self.id_pesanan = int(cur.lastrowid)
                res = self.id_pesanan
            conn.commit()
            return int(res)
        finally:
            cur.close()
            conn.close()

    def update_status(self, new_status: str) -> int:
        if not self.id_pesanan or self.id_pesanan == 0:
            raise ValueError("Id pesanan belum diset")
        
        allowed = fetch_allowed_statuses()
        if new_status not in allowed:
            raise ValueError(f"Status tidak valid: {new_status}")
            
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("UPDATE PesananWarung SET Status=%s WHERE IdPesananWarung=%s", (new_status, self.id_pesanan))
            conn.commit()
            self.status = new_status
            return int(cur.rowcount)
        finally:
            cur.close()
            conn.close()

    def cancel(self, restock: bool = True) -> int:
        if not self.id_pesanan or self.id_pesanan == 0:
            raise ValueError("Id pesanan belum diset")
            
        conn = get_db_connection()
        
        # === PERBAIKAN DI SINI ===
        # Mulai transaksi SEBELUM cursor atau query apapun dijalankan
        try:
            conn.start_transaction()
        except Exception:
            # Jika driver otomatis start transaction, ignore error ini
            pass
        # =========================

        cur = conn.cursor(dictionary=True)
        try:
            # Query SELECT dijalankan setelah transaksi dimulai
            cur.execute("SELECT Status FROM PesananWarung WHERE IdPesananWarung=%s", (self.id_pesanan,))
            row = cur.fetchone()
            if not row:
                raise ValueError("Pesanan tidak ditemukan")
            
            current_status = row.get("Status") if isinstance(row, dict) else row[0]
            if current_status in ("Dibatalkan", "Selesai", "Ditolak"):
                return 0

            # (HAPUS conn.start_transaction() YANG ADA DI TENGAH SINI)
            
            if restock:
                cur.execute("SELECT IdMakanan, BanyakPesanan FROM Pesanan WHERE IdPesananWarung=%s", (self.id_pesanan,))
                details_rows = cur.fetchall() or []
                for d in details_rows:
                    if isinstance(d, dict):
                        mid = d.get("IdMakanan"); jumlah = d.get("BanyakPesanan")
                    else:
                        mid = d[0]; jumlah = d[1]
                    
                    cur.execute("UPDATE Makanan SET Stok = COALESCE(Stok,0) + %s WHERE IdMakanan=%s", (jumlah, mid))
            
            cur.execute("UPDATE PesananWarung SET Status=%s WHERE IdPesananWarung=%s", ("Dibatalkan", self.id_pesanan))
            conn.commit()
            
            self.status = "Dibatalkan"
            return 1
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            cur.close()
            conn.close()
    def batalkan_pesanan(self, alasan: str) -> bool:
        
        if not self.id_pesanan or self.id_pesanan == 0:
            raise ValueError("Id pesanan belum diset")
        if not alasan or not alasan.strip():
            raise ValueError("Alasan pembatalan wajib diisi")
            
        conn = get_db_connection()
        
        try:
            conn.start_transaction()
        except Exception:
            pass

        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT Status FROM PesananWarung WHERE IdPesananWarung=%s FOR UPDATE", (self.id_pesanan,))
            row = cur.fetchone()
            
            if not row:
                raise ValueError("Pesanan tidak ditemukan")
            
            current_status = row.get("Status") if isinstance(row, dict) else row[0]
            
            status_terlarang = ("Diproses", "Diantar", "Selesai", "Ditolak", "Dibatalkan")
            
            if current_status in status_terlarang:
                return False

            cur.execute("SELECT IdMakanan, BanyakPesanan FROM Pesanan WHERE IdPesananWarung=%s", (self.id_pesanan,))
            details_rows = cur.fetchall() or []
            
            update_stok_sql = "UPDATE Makanan SET Stok = COALESCE(Stok,0) + %s WHERE IdMakanan=%s"
            
            for d in details_rows:
                if isinstance(d, dict):
                    mid = d.get("IdMakanan"); jumlah = d.get("BanyakPesanan")
                else:
                    mid = d[0]; jumlah = d[1]
                
                cur.execute(update_stok_sql, (jumlah, mid))
            
            update_sql = """
                UPDATE PesananWarung 
                SET Status=%s, DeskripsiPesanan=%s 
                WHERE IdPesananWarung=%s
            """
            cur.execute(update_sql, ("Dibatalkan", alasan, self.id_pesanan))
            
            conn.commit()
            
            self.status = "Dibatalkan"
            self.catatan = alasan
            return True
            
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            cur.close()
            conn.close()

    def tolak_pesanan(self, alasan: str) -> bool:
        """
        Menolak pesanan: Mengembalikan stok, mengubah status ke 'Ditolak',
        dan menyimpan alasan ke kolom DeskripsiPesanan.
        """
        if not self.id_pesanan or self.id_pesanan == 0:
            raise ValueError("Id pesanan belum diset")
        if not alasan or not alasan.strip():
            raise ValueError("Alasan penolakan wajib diisi")
            
        conn = get_db_connection()
        try:
            conn.start_transaction()
        except Exception:
            pass # Ignore if transaction started automatically

        cur = conn.cursor(dictionary=True)
        try:
            # 1. Cek Status Terkini (Lock row)
            cur.execute("SELECT Status FROM PesananWarung WHERE IdPesananWarung=%s FOR UPDATE", (self.id_pesanan,))
            row = cur.fetchone()
            
            if not row:
                raise ValueError("Pesanan tidak ditemukan")
            
            current_status = row.get("Status") if isinstance(row, dict) else row[0]
            
            # Jika pesanan sudah selesai/batal/tolak, hentikan
            if current_status in ("Dibatalkan", "Selesai", "Ditolak"):
                return False

            # 2. Restock (Kembalikan Stok Makanan)
            cur.execute("SELECT IdMakanan, BanyakPesanan FROM Pesanan WHERE IdPesananWarung=%s", (self.id_pesanan,))
            details_rows = cur.fetchall() or []
            
            update_stok_sql = "UPDATE Makanan SET Stok = COALESCE(Stok,0) + %s WHERE IdMakanan=%s"
            
            for d in details_rows:
                if isinstance(d, dict):
                    mid = d.get("IdMakanan")
                    jumlah = d.get("BanyakPesanan")
                else:
                    mid = d[0]
                    jumlah = d[1]
                
                cur.execute(update_stok_sql, (jumlah, mid))
            
            # 3. Update Status dan Deskripsi
            update_sql = """
                UPDATE PesananWarung 
                SET Status=%s, DeskripsiPesanan=%s 
                WHERE IdPesananWarung=%s
            """
            cur.execute(update_sql, ("Ditolak", alasan, self.id_pesanan))
            
            conn.commit()
            
            self.status = "Ditolak"
            self.catatan = alasan
            return True
            
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            cur.close()
            conn.close()
    def mark_paid(self, payment_method: str = "Cash") -> int:
        if not self.id_pesanan or self.id_pesanan == 0:
            raise ValueError("Id pesanan belum diset")
        if not payment_method:
            raise ValueError("Metode pembayaran tidak boleh kosong")

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            updated = 0
            now = datetime.now()
            
            try:
                cur.execute(
                    "UPDATE PesananWarung SET Status=%s, MetodePembayaran=%s, TanggalPembayaran=%s WHERE IdPesananWarung=%s",
                    ("Menunggu", str(payment_method), now, int(self.id_pesanan))
                )
                updated = cur.rowcount
            except Exception:
                try:
                    cur.execute("UPDATE PesananWarung SET Status=%s WHERE IdPesananWarung=%s",
                                ("Menunggu", int(self.id_pesanan)))
                    updated = cur.rowcount
                except Exception:
                    raise

            conn.commit()
            if updated:
                self.status = "Menunggu"
            return int(updated)
        finally:
            cur.close()
            conn.close()


def fetch_allowed_statuses() -> Set[str]:
    return {
        "Pembayaran", 
        "Menunggu", 
        "Diproses", 
        "Diantar",   
        "Selesai", 
        "Ditolak", 
        "Dibatalkan", 
        "Dibayar"
    }

def get_pesanan_by_user(id_pembeli: int, limit: int = 50, offset: int = 0) -> List[Pesanan]:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        sql = """
            SELECT pw.IdPesananWarung, pw.IdPembeli, pw.IdWarung, pw.TotalHarga, 
                   pw.DeskripsiPesanan, pw.Status, pw.DibuatPada,
                   w.NamaWarung
            FROM PesananWarung pw
            JOIN Warung w ON pw.IdWarung = w.IdWarung
            WHERE pw.IdPembeli=%s 
            ORDER BY pw.IdPesananWarung DESC LIMIT %s OFFSET %s
        """
        cur.execute(sql, (id_pembeli, limit, offset))
        
        rows = cur.fetchall() or []
        hasil: List[Pesanan] = []
        for r in rows:
            waktu = r.get("DibuatPada")
            waktu_str = (waktu.isoformat() if hasattr(waktu, "isoformat") else str(waktu))
            
            warung_obj = Warung(
                id_warung=int(r["IdWarung"]),
                nama_warung=str(r.get("NamaWarung") or "Warung")
            )

            p = Pesanan(
                id_pesanan=int(r["IdPesananWarung"]),
                id_pembeli=int(r["IdPembeli"]),
                id_warung=int(r["IdWarung"]),
                total_harga=float(r.get("TotalHarga") or 0.0),
                status=str(r.get("Status") or ""),
                catatan=str(r.get("DeskripsiPesanan") or ""),
                waktu_dibuat=waktu_str,
                details=[],
                warung=warung_obj 
            )
            hasil.append(p)
        return hasil
    finally:
        cur.close()
        conn.close()

def get_pesanan_for_seller(id_warung: int, status_filter: str = None) -> List[Pesanan]:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        query = """
            SELECT pw.IdPesananWarung, pw.IdPembeli, pw.IdWarung, pw.TotalHarga, 
                   pw.DeskripsiPesanan, pw.Status, pw.DibuatPada,
                   p.NamaPengguna as NamaPembeli
            FROM PesananWarung pw
            JOIN Pengguna p ON pw.IdPembeli = p.IdPengguna
            WHERE pw.IdWarung = %s
        """
        params = [id_warung]

        if status_filter and status_filter != 'Semua':
            query += " AND pw.Status = %s"
            params.append(status_filter)

        query += " ORDER BY pw.DibuatPada DESC"

        cur.execute(query, tuple(params))
        rows = cur.fetchall() or []

        hasil: List[Pesanan] = []
        for r in rows:
            waktu = r.get("DibuatPada")
            waktu_str = (waktu.isoformat() if hasattr(waktu, "isoformat") else str(waktu))

            pesanan_obj = Pesanan(
                id_pesanan=int(r["IdPesananWarung"]),
                id_pembeli=int(r["IdPembeli"]),
                id_warung=int(r["IdWarung"]),
                total_harga=float(r.get("TotalHarga") or 0.0),
                status=str(r.get("Status") or ""),
                catatan=str(r.get("DeskripsiPesanan") or ""),
                waktu_dibuat=waktu_str,
                details=[]
            )
            pesanan_obj.nama_pembeli = r.get("NamaPembeli") or "Pelanggan"
            hasil.append(pesanan_obj)
            
        return hasil
    except Exception:
        return []
    finally:
        cur.close()
        conn.close()

def get_pesanan_detail(id_pesanan: int) -> Dict[str, Any]:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT pw.*, w.NamaWarung 
            FROM PesananWarung pw 
            JOIN Warung w ON pw.IdWarung = w.IdWarung
            WHERE pw.IdPesananWarung=%s
        """, (id_pesanan,))
        pw = cur.fetchone()
        if not pw:
            return {}
        
        cur.execute("""
            SELECT p.IdPesanan, p.IdMakanan, p.BanyakPesanan, p.Subtotal,
                   m.NamaMakanan, m.HargaMakanan, m.GambarMakanan
            FROM Pesanan p
            LEFT JOIN Makanan m ON m.IdMakanan = p.IdMakanan
            WHERE p.IdPesananWarung=%s
        """, (id_pesanan,))
        details = cur.fetchall() or []
        
        return {
            "pesanan": pw,
            "details": details
        }
    finally:
        cur.close()
        conn.close()

def delete_user_carts(user_id: int) -> int:
    if not user_id:
        return 0
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        conn.start_transaction()
        cur.execute("SELECT IdPesananWarung FROM PesananWarung WHERE IdPembeli=%s AND Status=%s",
                    (int(user_id), "Pembayaran"))
        rows = cur.fetchall() or []
        
        ids = []
        for r in rows:
            val = r[0] if isinstance(r, (list, tuple)) else (r.get("IdPesananWarung") if isinstance(r, dict) else r)
            if val: ids.append(int(val))

        if ids:
            placeholders = ",".join(["%s"] * len(ids))
            cur.execute(f"DELETE FROM Pesanan WHERE IdPesananWarung IN ({placeholders})", tuple(ids))
            cur.execute(f"DELETE FROM PesananWarung WHERE IdPesananWarung IN ({placeholders})", tuple(ids))
            
        conn.commit()
        return len(ids)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        cur.close()
        conn.close()
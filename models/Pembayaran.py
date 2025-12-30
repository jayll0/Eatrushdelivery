# models/Pembayaran.py
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from .db import get_db_connection
from datetime import datetime

# Allowed methods (extendable)
ALLOWED_PAYMENT_METHODS = {"Cash", "QRIS", "Bank Transfer", "E-Wallet", "Midtrans"}

@dataclass
class Pembayaran:
    id_pembayaran: Optional[int]
    id_pesanan: int
    metode: str
    jumlah: float
    waktu: str
    status: str  # "Pending", "Berhasil", "Gagal"
    rincian: Optional[str] = None  # optional note / gateway metadata

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -------------------------
# DB helper functions
# -------------------------

def _insert_payment_record(conn, cur, id_pesanan: int, metode: str, jumlah: float, rincian: Optional[str]=None) -> int:
    """
    Insert row into Pembayaran table and return inserted id.
    Assumes caller manages transaction/conn.
    """
    insert_sql = """
        INSERT INTO Pembayaran (IdPesananWarung, Metode, Jumlah, Waktu, Status, Rincian)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    waktu = datetime.now()
    status = "Pending"
    cur.execute(insert_sql, (id_pesanan, metode, jumlah, waktu, status, rincian))
    return cur.lastrowid


def _update_payment_status(conn, cur, id_pembayaran: int, new_status: str):
    cur.execute("UPDATE Pembayaran SET Status=%s WHERE IdPembayaran=%s", (new_status, id_pembayaran))


# -------------------------
# Public API
# -------------------------

def create_payment_record(id_pesanan: int, metode: str, jumlah: float, rincian: Optional[str] = None) -> int:
    """
    Create a payment record in DB with status 'Pending'.
    Returns inserted payment id.
    """
    if metode not in ALLOWED_PAYMENT_METHODS:
        raise ValueError(f"Metode pembayaran tidak valid: {metode}")

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        pid = _insert_payment_record(conn, cur, id_pesanan, metode, jumlah, rincian)
        conn.commit()
        return pid
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def confirm_payment_and_mark_paid(id_pembayaran: int, expected_amount: Optional[float] = None) -> bool:
    """
    Confirm a pending payment (set Pembayaran.Status='Berhasil') and atomically mark the related
    PesananWarung as 'Dibayar' if amounts match (or if expected_amount is None, skip strict match).
    Returns True if successful (status set to Berhasil); raises on error.
    """
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()

        # fetch payment row
        cur.execute("SELECT IdPembayaran, IdPesananWarung, Metode, Jumlah, Status FROM Pembayaran WHERE IdPembayaran=%s FOR UPDATE", (id_pembayaran,))
        pay = cur.fetchone()
        if not pay:
            raise ValueError("Pembayaran tidak ditemukan")

        if pay.get("Status") == "Berhasil":
            # already confirmed
            conn.commit()
            return True

        id_pesanan = pay.get("IdPesananWarung")
        jumlah = float(pay.get("Jumlah") or 0.0)

        # optional: verify payment amount matches pesanan total
        if expected_amount is not None and float(expected_amount) != float(jumlah):
            raise ValueError(f"Jumlah pembayaran ({jumlah}) tidak sesuai dengan jumlah yang diharapkan ({expected_amount})")

        # read pesanan total (lock row)
        cur.execute("SELECT IdPesananWarung, TotalHarga, Status FROM PesananWarung WHERE IdPesananWarung=%s FOR UPDATE", (id_pesanan,))
        pw = cur.fetchone()
        if not pw:
            raise ValueError("Pesanan terkait tidak ditemukan")

        total_harga = float(pw.get("TotalHarga") or 0.0)
        status_pesanan = pw.get("Status")

        # Option: ensure amount equals total_harga (prevent underpayment)
        # Here we require jumlah >= total_harga; change to == if you want strict equality.
        if jumlah < total_harga:
            raise ValueError("Jumlah pembayaran kurang dari total pesanan")

        # update pembayaran status -> Berhasil
        _update_payment_status(conn, cur, id_pembayaran, "Berhasil")

        # update pesanan status -> Dibayar (only if not already paid)
        if status_pesanan != "Dibayar":
            cur.execute("UPDATE PesananWarung SET Status=%s WHERE IdPesananWarung=%s", ("Dibayar", id_pesanan))

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def mark_payment_failed(id_pembayaran: int, reason: Optional[str] = None) -> bool:
    """
    Set payment status to 'Gagal' and optionally store reason in rincian.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        conn.start_transaction()
        cur.execute("UPDATE Pembayaran SET Status=%s, Rincian=%s WHERE IdPembayaran=%s", ("Gagal", reason, id_pembayaran))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def get_payment_by_id(id_pembayaran: int) -> Optional[Pembayaran]:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT IdPembayaran, IdPesananWarung, Metode, Jumlah, Waktu, Status, Rincian FROM Pembayaran WHERE IdPembayaran=%s", (id_pembayaran,))
        r = cur.fetchone()
        if not r:
            return None
        return Pembayaran(
            id_pembayaran=r.get("IdPembayaran"),
            id_pesanan=r.get("IdPesananWarung"),
            metode=r.get("Metode"),
            jumlah=float(r.get("Jumlah") or 0.0),
            waktu=(r.get("Waktu").isoformat() if hasattr(r.get("Waktu"), "isoformat") else r.get("Waktu")),
            status=r.get("Status"),
            rincian=r.get("Rincian")
        )
    finally:
        cur.close()
        conn.close()


def list_payments_for_pesanan(id_pesanan: int) -> List[Pembayaran]:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT IdPembayaran, IdPesananWarung, Metode, Jumlah, Waktu, Status, Rincian FROM Pembayaran WHERE IdPesananWarung=%s ORDER BY IdPembayaran DESC", (id_pesanan,))
        rows = cur.fetchall() or []
        out = []
        for r in rows:
            out.append(Pembayaran(
                id_pembayaran=r.get("IdPembayaran"),
                id_pesanan=r.get("IdPesananWarung"),
                metode=r.get("Metode"),
                jumlah=float(r.get("Jumlah") or 0.0),
                waktu=(r.get("Waktu").isoformat() if hasattr(r.get("Waktu"), "isoformat") else r.get("Waktu")),
                status=r.get("Status"),
                rincian=r.get("Rincian")
            ))
        return out
    finally:
        cur.close()
        conn.close()

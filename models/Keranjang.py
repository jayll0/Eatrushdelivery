from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple, Optional
from flask import session, current_app
from models.Makanan import Makanan

@dataclass
class Keranjang:
    id_makanan: int
    id_warung: int
    nama: str
    harga: float
    qty: int = 1
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def normalize_item(raw: Dict[str, Any]) -> Keranjang:
    if not raw:
        raise ValueError("Payload item kosong")
    try:
        id_makanan = int(raw.get("id_makanan") or raw.get("id") or 0)
    except Exception:
        id_makanan = 0
    if id_makanan <= 0:
        raise ValueError("id_makanan tidak valid")
    try:
        qty = max(1, int(raw.get("qty", 1)))
    except Exception:
        qty = 1
    note = str(raw.get("note", "") or "").strip()

    m = Makanan().get_by_id(id_makanan)
    if not m:
        raise ValueError("Makanan tidak ditemukan")
    try:
        id_warung = int(m.get_id_warung())
    except Exception:
        raise ValueError("Data warung makanan tidak valid")
    try:
        nama = str(m.get_nama_makanan() or "")
    except Exception:
        nama = ""
    try:
        harga = float(m.get_harga_makanan() or 0.0)
    except Exception:
        harga = 0.0

    return Keranjang(
        id_makanan=id_makanan,
        id_warung=id_warung,
        nama=nama,
        harga=harga,
        qty=qty,
        note=note,
    )

def find_index(cart: List[Dict[str, Any]], id_makanan: int, note: Optional[str] = None) -> Tuple[int, Optional[Dict[str, Any]]]:
    target_id = int(id_makanan)
    target_note = str(note).strip() if note is not None else None

    for i, it in enumerate(cart):
        try:
            current_id = int(it.get('id_makanan') or it.get('id') or 0)
            current_note = str(it.get('note', '') or '').strip()

            if current_id == target_id:
                if target_note is not None:
                    if current_note == target_note:
                        return i, it
                else:
                    return i, it
        except Exception:
            continue
    return -1, None

def check_stock(id_makanan: int, requested_qty: int) -> Tuple[bool, int]:
    m = Makanan().get_by_id(id_makanan)
    if not m:
        return False, 0
    try:
        stok = int(m.get_stok_makanan() or 0)
    except Exception:
        stok = 0
    return (stok >= int(requested_qty)), stok

def _get_server_cart_all() -> Dict[str, List[Dict[str, Any]]]:
    v = session.get('server_cart')
    if not isinstance(v, dict):
        return {}
    return v

def _get_server_cart_raw(warung_id: int) -> List[Dict[str, Any]]:
    return _get_server_cart_all().get(str(warung_id), [])

def _set_server_cart_raw(warung_id: int, cart_list: List[Dict[str, Any]]):
    all_cart = _get_server_cart_all()
    all_cart[str(warung_id)] = cart_list
    session['server_cart'] = all_cart
    session.modified = True

def _remove_server_cart_for_warung(warung_id: int):
    all_cart = _get_server_cart_all()
    if str(warung_id) in all_cart:
        all_cart.pop(str(warung_id), None)
        session['server_cart'] = all_cart
        session.modified = True

def _get_session_cart_warung_ids() -> List[int]:
    ks = []
    for k in _get_server_cart_all().keys():
        try:
            ks.append(int(k))
        except Exception:
            continue
    return ks

def _ensure_db_store():
    if 'DB_CARTS' not in current_app.config:
        current_app.config['DB_CARTS'] = {}

def _delete_all_db_carts_for_user_inmemory(user_id: int) -> None:
    try:
        _ensure_db_store()
        db = current_app.config['DB_CARTS']
        db.pop(int(user_id), None)
    except Exception:
        pass

def _create_or_replace_cart_inmemory(id_pembeli: int, id_warung: int, items: List[Dict[str, Any]]) -> None:
    try:
        _ensure_db_store()
        db = current_app.config['DB_CARTS']
        uid = int(id_pembeli)
        wid = int(id_warung)
        if uid not in db:
            db[uid] = {}
        clean_items = []
        for it in items or []:
            try:
                clean_items.append({
                    "id_makanan": int(it.get("id_makanan") or it.get("id") or 0),
                    "qty": max(1, int(it.get("qty", 1))),
                    "note": str(it.get("note", "") or "")
                })
            except Exception:
                continue
        if clean_items:
            db[uid][wid] = clean_items
        else:
            db[uid].pop(wid, None)
    except Exception:
        pass

def _get_db_mode() -> bool:
    return bool(current_app.config.get('CART_USE_DB', False))

def delete_user_carts_db(user_id: int) -> None:
    try:
        from .db import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE p FROM Pesanan p "
            "JOIN PesananWarung pw ON p.IdPesananWarung = pw.IdPesananWarung "
            "WHERE pw.IdPembeli = %s AND pw.Status = %s",
            (int(user_id), 'Keranjang')
        )
        cur.execute(
            "DELETE FROM PesananWarung WHERE IdPembeli = %s AND Status = %s",
            (int(user_id), 'Keranjang')
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

def create_or_replace_cart_db(id_pembeli: int, id_warung: int, items: List[Dict[str, Any]]) -> Tuple[bool, str]:
    if not isinstance(items, list):
        return False, "Items harus list"
    
    total_harga = 0.0
    prepared = []
    stok_map = {}

    for it in items:
        try:
            mid = int(it.get("id_makanan") or it.get("id") or 0)
            qty = max(1, int(it.get("qty", 1)))
            stok_map[mid] = stok_map.get(mid, 0) + qty
        except Exception:
            return False, "Format item tidak valid"

    for mid, total_req in stok_map.items():
        ok, sisa = check_stock(mid, total_req)
        if not ok:
            return False, f"Stok tidak cukup untuk id={mid} (Diminta: {total_req}, Sisa: {sisa})"

    for it in items:
        try:
            mid = int(it.get("id_makanan") or 0)
            qty = max(1, int(it.get("qty", 1)))
            note = str(it.get("note", "") or "")
        except Exception:
            continue
        
        m = Makanan().get_by_id(mid)
        if not m:
            return False, f"Makanan id={mid} tidak ditemukan"
        
        try:
            harga = float(m.get_harga_makanan() or 0.0)
        except Exception:
            harga = 0.0
        
        subtotal = harga * qty
        total_harga += subtotal
        prepared.append((mid, qty, note, harga, subtotal))

    try:
        from .db import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            "DELETE p FROM Pesanan p JOIN PesananWarung pw ON p.IdPesananWarung = pw.IdPesananWarung WHERE pw.IdPembeli=%s AND pw.Status='Keranjang'",
            (int(id_pembeli),)
        )
        cur.execute("DELETE FROM PesananWarung WHERE IdPembeli=%s AND Status='Keranjang'", (int(id_pembeli),))

        if not prepared:
            conn.commit()
            cur.close()
            conn.close()
            return True, "Keranjang dikosongkan"

        cur.execute(
            "INSERT INTO PesananWarung (IdPembeli, IdWarung, TotalHarga, Status, DeskripsiPesanan) VALUES (%s, %s, %s, %s, %s)",
            (int(id_pembeli), int(id_warung), float(total_harga), 'Keranjang', 'Keranjang sementara')
        )
        id_pesanan_warung = cur.lastrowid
        
        for mid, qty, note, harga, subtotal in prepared:
            cur.execute(
                "INSERT INTO Pesanan (IdPesananWarung, IdMakanan, BanyakPesanan, Subtotal) VALUES (%s, %s, %s, %s)",
                (int(id_pesanan_warung), int(mid), int(qty), float(subtotal))
            )
            
        conn.commit()
        cur.close()
        conn.close()
        return True, "Cart DB dibuat"
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False, "Gagal menyimpan cart ke DB"

def _delete_all_db_carts_for_user(user_id: int) -> None:
    try:
        if _get_db_mode():
            delete_user_carts_db(user_id=int(user_id))
        else:
            _delete_all_db_carts_for_user_inmemory(user_id=int(user_id))
    except Exception:
        pass

def _upsert_db_cart_from_session(user_id: int, warung_id: int) -> None:
    try:
        server_cart = _get_server_cart_raw(warung_id) or []
        items = []
        for it in server_cart:
            try:
                mid = int(it.get("id_makanan") or it.get("id") or 0)
                qty = max(1, int(it.get("qty", 1)))
                note = it.get("note", "") or ""
                items.append({"id_makanan": mid, "qty": qty, "note": note})
            except Exception:
                continue
        if _get_db_mode():
            create_or_replace_cart_db(id_pembeli=int(user_id), id_warung=int(warung_id), items=items)
        else:
            _create_or_replace_cart_inmemory(id_pembeli=int(user_id), id_warung=int(warung_id), items=items)
    except Exception:
        pass

def add_item_to_server_cart(payload: Dict[str, Any], user_id: int) -> Tuple[bool, str]:
    try:
        item = normalize_item(payload)
    except Exception as e:
        return False, f"Payload item tidak valid: {e}"

    warung_id = int(item.id_warung)

    existing_warung_ids = _get_session_cart_warung_ids()
    other_warungs = [wid for wid in existing_warung_ids if wid != warung_id]
    
    switched_from = None
    if other_warungs:
        switched_from = other_warungs[0]
        try:
            for wid in other_warungs:
                _remove_server_cart_for_warung(wid)
        except Exception:
            pass
        try:
            _delete_all_db_carts_for_user(user_id=user_id)
        except Exception:
            pass

    cart = _get_server_cart_raw(warung_id)
    
    current_id_usage = sum(int(x.get('qty', 0)) for x in cart if int(x.get('id_makanan', 0)) == int(item.id_makanan))
    total_needed = current_id_usage + int(item.qty)

    ok, avail = check_stock(item.id_makanan, total_needed)
    if not ok:
        return False, f"Stok tidak cukup (tersisa {avail})"

    idx, existing = find_index(cart, item.id_makanan, item.note)
    
    if idx >= 0 and existing:
        existing_qty = int(existing.get("qty", 0))
        existing['qty'] = existing_qty + int(item.qty)
        cart[idx] = existing
    else:
        cart.append(item.to_dict())
        
    _set_server_cart_raw(warung_id, cart)

    try:
        _delete_all_db_carts_for_user(user_id=user_id)
    except Exception:
        pass

    try:
        _upsert_db_cart_from_session(user_id=user_id, warung_id=warung_id)
    except Exception:
        pass

    if switched_from:
        return True, f"Item ditambahkan. Cart sebelumnya untuk warung {switched_from} dihapus."
    return True, "Item berhasil ditambahkan."

def update_qty_in_server_cart(warung_id: int, id_makanan: int, qty: int, user_id: int, note: str = "") -> Tuple[bool, str]:
    cart = _get_server_cart_raw(warung_id)
    idx, existing = find_index(cart, id_makanan, note)
    
    if idx < 0 or existing is None:
        return False, "Item tidak ditemukan di keranjang."
        
    if qty <= 0:
        return remove_item_from_server_cart(warung_id, id_makanan, user_id, note)

    other_usage = 0
    for i, it in enumerate(cart):
        if i != idx and int(it.get('id_makanan', 0)) == int(id_makanan):
            other_usage += int(it.get('qty', 0))
            
    total_needed = other_usage + qty
    ok, stok = check_stock(id_makanan, total_needed)
    if not ok:
        return False, f"Stok tidak cukup. Tersisa {stok}."

    existing['qty'] = int(qty)
    cart[idx] = existing
    _set_server_cart_raw(warung_id, cart)
    
    try:
        _upsert_db_cart_from_session(user_id=user_id, warung_id=warung_id)
    except Exception:
        pass
    return True, "Jumlah diupdate."

def remove_item_from_server_cart(warung_id: int, id_makanan: int, user_id: int, note: str = "") -> Tuple[bool, str]:
    cart = _get_server_cart_raw(warung_id)
    idx, _ = find_index(cart, id_makanan, note)
    
    if idx < 0:
        return False, "Item tidak ditemukan."
    
    cart.pop(idx)
    
    if not cart:
        _remove_server_cart_for_warung(warung_id)
    else:
        _set_server_cart_raw(warung_id, cart)
        
    try:
        _upsert_db_cart_from_session(user_id=user_id, warung_id=warung_id)
    except Exception:
        pass
    return True, "Item dihapus."

def get_cart_total(warung_id: int) -> Dict[str, Any]:
    cart = _get_server_cart_raw(warung_id)
    total = 0.0
    count_items = 0
    for it in cart:
        try:
            harga = float(it.get('harga') or 0)
            qty = int(it.get('qty') or 0)
            total += harga * qty
            count_items += qty
        except Exception:
            continue
    return {"subtotal": total, "count_items": count_items}

def cart_to_list(cart_items: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not cart_items:
        return out
    for it in cart_items:
        try:
            if hasattr(it, "to_dict") and callable(getattr(it, "to_dict")):
                out.append(it.to_dict())
            elif isinstance(it, dict):
                d = {
                    "id_makanan": int(it.get("id_makanan") or it.get("id") or 0),
                    "id_warung": int(it.get("id_warung") or it.get("warung") or 0),
                    "nama": str(it.get("nama") or it.get("name") or ""),
                    "harga": float(it.get("harga") or it.get("price") or 0.0),
                    "qty": int(it.get("qty") or 1),
                    "note": str(it.get("note") or ""),
                }
                out.append(d)
            else:
                id_m = getattr(it, "id_makanan", None) or getattr(it, "id", None)
                wid = getattr(it, "id_warung", None) or getattr(it, "warung", None)
                nama = getattr(it, "nama", None) or getattr(it, "name", None) or ""
                harga = getattr(it, "harga", None) or getattr(it, "price", None) or 0.0
                qty = getattr(it, "qty", 1)
                note = getattr(it, "note", "") or ""
                out.append({
                    "id_makanan": int(id_m or 0),
                    "id_warung": int(wid or 0),
                    "nama": str(nama),
                    "harga": float(harga or 0.0),
                    "qty": int(qty or 1),
                    "note": str(note),
                })
        except Exception:
            continue
    return out
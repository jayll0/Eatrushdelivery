from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict, Optional

@dataclass
class ItemLaporan:
    id_pesanan: int
    total_harga: Decimal
    status: str 
    dibuat_pada: datetime

@dataclass
class Laporan:
    id_warung: int
    transaksi_list: List[ItemLaporan] = field(default_factory=list)
    def getTotalPendapatan(self, start_date: Optional[date] = None) -> Decimal:
        total_pendapatan = Decimal('0.00')
        
        for item in self.transaksi_list:
            if item.status == 'Selesai':
                if start_date and item.dibuat_pada.date() < start_date:
                    continue

                total_pendapatan += item.total_harga
                
        return total_pendapatan
    def getTotalPesanan(self, start_date: Optional[date] = None) -> int:
        total_pesanan_selesai = 0
        for item in self.transaksi_list:
            if item.status == 'Selesai':
                if start_date and item.dibuat_pada.date() < start_date:
                    continue

                total_pesanan_selesai += 1
                
        return total_pesanan_selesai

    def sortPesanan(self) -> Dict[str, Decimal]:
        laporan_harian = {}
        sorted_data = sorted(self.transaksi_list, key=lambda x: x.dibuat_pada)

        for item in sorted_data:
            if item.status == 'Selesai':
                tanggal_key = item.dibuat_pada.strftime('%Y-%m-%d')
                
                if tanggal_key not in laporan_harian:
                    laporan_harian[tanggal_key] = Decimal('0.00')
                
                laporan_harian[tanggal_key] += item.total_harga

        return laporan_harian
# Format File Upload OptiQM Studio

OptiQM Studio menerima **Excel (`.xlsx`, `.xlsm`)**, **CSV/TSV (`.csv`, `.tsv`, `.txt`)**, **JSON (`.json`, `.oqm`)**, dan **link Google Sheets publik**.

## 1. Banyak Modul dalam 1 File Excel
Setiap **sheet** di dalam file `.xlsx` mewakili 1 kasus modul. Modul dikenali otomatis dari:
1. Baris `module` di blok `[params]`, **atau**
2. Awalan nama sheet (contoh: `LP_Produksi`, `TRANS_Gudang`, `FC_Penjualan`, `EOQ_Bahan`, `PERT_Proyek`, `QUEUE_Kasir`, `DT_Keputusan`, `BEP_Produk`).

## 2. Tata Letak Isi Sheet

### Cara Sederhana (tanpa penanda)
Langsung tulis tabel pada baris pertama dengan header kolom, contoh sheet `LP_Produksi`:

| Name | X1 | X2 | Sign | RHS |
|---|---|---|---|---|
| Objective | 50 | 40 | | |
| Perakitan | 3 | 5 | <= | 150 |

### Cara Lengkap (dengan penanda `[params]` dan `[main]`)
Gunakan penanda `[...]` bila ingin mengatur parameter skalar atau menyertakan beberapa tabel (mis. `[flows]` dan `[distances]` pada Operations Layout, atau `[bom]`, `[items]`, `[mps]` pada MRP):

```
[params]
module    | transportation
objective | min
initial_method | vogel

[main]
Source   | Gudang 1 | Gudang 2 | Supply
Pabrik A | 5        | 4        | 100
Demand   | 60       | 40       |
```

> Unduh template siap pakai langsung dari aplikasi lewat tombol **Sample 10-Modul (.xlsx)** atau tombol template per modul.

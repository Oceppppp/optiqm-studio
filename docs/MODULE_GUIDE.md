# Panduan Membuat Modul OptiQM

Setiap modul = satu sub-package di `backend/optiqm/modules/<key>/` dan **otomatis
terdeteksi** oleh registry. Tidak perlu mengubah kode lain (API, UI, laporan).

## Struktur

```
backend/optiqm/modules/<key>/
├── __init__.py   # from .module import <Class>  # noqa: F401
├── module.py     # adapter: template(), solve(SheetData) -> ModuleResult   (≤ ~250 baris)
└── solver.py     # matematika murni (numpy/scipy/networkx), tanpa SheetData/I/O
backend/tests/modules/test_<key>.py
```

Pecah lebih lanjut (mis. `methods.py`, `charts.py`) bila sebuah file mendekati 300 baris.

## Kontrak

```python
from optiqm.core import BaseModule, InputError, SolverError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, numeric_column, numeric_matrix, to_float, require_rows

@register
class MyModule(BaseModule):
    key = "my_module"                 # snake_case unik
    name = "Nama Tampilan"            # istilah standar (boleh Inggris spt POM-QM)
    category = "Kategori"             # lihat daftar kategori di bawah
    description = "Satu kalimat Bahasa Indonesia."
    sheet_prefixes = ("MYM",)         # prefix nama sheet Excel utk auto-detect (UNIK)
    params = (ParamSpec("method", "Metode", "choice", "a", ("a", "b")), ...)
    table_hint = "Penjelasan format tabel [main] untuk pengguna."

    def template(self) -> SheetData:   # soal contoh valid (dari buku teks bila bisa)
        return SheetData(params={...}, tables={"main": pd.DataFrame(...)})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)          # dict param sudah dikonversi tipe + default
        df = clean_frame(data.table("main"))    # tabel opsional: data.table("x", required=False)
        ...
        r = ModuleResult()
        r.metric("Total Biaya", 1234.5, unit="Rp", highlight=True)
        r.table("Judul", ["Kol1", "Kol2"], [[...], ...])
        r.chart("Judul", "line", {...})         # kind: line|bar|area|scatter|lp_region|network|gantt
        r.steps.append(Table(...))              # opsional: langkah iterasi
        r.warnings.append("...")                # opsional
        r.interpretation = "Kalimat ringkas hasil dalam Bahasa Indonesia."
        return r
```

Format `data` setiap jenis chart didokumentasikan di `backend/optiqm/core/result.py`.

## Aturan

1. **Data masuk hanya via `SheetData`** (params + tabel). Parameter skalar ⇒ `params`; data berulang ⇒ tabel.
2. Validasi input dengan pesan jelas Bahasa Indonesia ⇒ `raise InputError(...)`. Kegagalan matematis ⇒ `SolverError`.
3. Hasil harus **sama dengan POM-QM / buku teks** (Heizer & Render, Render-Stair-Hanna, Taylor). Tulis test dengan angka acuan.
4. Toleransi input: gunakan `find_column` (sinonim kolom), `to_float` (koma desimal, persen).
5. Template harus bisa langsung di-`solve()` tanpa error (diuji otomatis).
6. Jangan mengubah `optiqm/core/*`. Jika butuh fitur core baru, laporkan ke orchestrator.
7. Label UI/teks hasil: Bahasa Indonesia; nama metode boleh istilah Inggris standar.

## Kategori

`Pemrograman Matematis`, `Distribusi & Jaringan`, `Peramalan`, `Persediaan`, `Perencanaan Produksi`,
`Manajemen Proyek`, `Antrian`, `Analisis Keputusan`, `Biaya & Keuangan`, `Kualitas & Keandalan`,
`Lokasi & Tata Letak`, `Penjadwalan`, `Produktivitas & Kerja`, `Statistik & Simulasi`.

## Menjalankan test

```bash
cd backend && ../.venv/bin/python -m pytest -q tests/modules/test_<key>.py
```

# OptiQM Studio

Suite **Metode Kuantitatif & Manajemen Operasi** modern — pengganti **POM‑QM for Windows** dengan tiga keunggulan utama:

1. **Jalankan Semua Fitur Sekaligus (Multi‑Modul & Batch Run)** — Aktifkan dan jalankan puluhan modul secara bersamaan dengan satu tombol **Run All**, tampilkan seluruh hasil berdampingan, lalu ekspor ke 1 laporan **Excel (.xlsx)** atau **PDF** gabungan.
2. **Input Lewat Upload File** — Unggah **Excel (`.xlsx` multi‑sheet)**, **CSV/TSV**, **JSON/OQM**, atau **link Google Sheets publik**. Setiap sheet terdeteksi otomatis sebagai modul yang sesuai dan tetap bisa diedit langsung di grid UI.
3. **Arsitektur Modular & Siap Pakai di Komputer Lain** — **43 modul** POM‑QM terpisah rapi dalam folder masing-masing (`backend/optiqm/modules/<key>/`) melalui plugin auto-discovery; dibungkus menjadi aplikasi desktop **Windows (`.exe`), macOS, & Linux** lewat GitHub Actions Releases.

## Menjalankan Secara Lokal

### Prasyarat
- Python ≥ 3.11
- Node.js ≥ 20 (untuk mode dev UI atau build frontend)

### Cara Cepat (Produksi / 1 Perintah)
```bash
cd frontend && npm install && npm run build && cd ..
python -m venv .venv && . .venv/bin/activate
pip install -e "./backend[dev]"
optiqm --port 8000
```
Buka `http://127.0.0.1:8000`.

### Mode Development (Backend + Vite Hot Reload)
```bash
# Terminal 1 (Backend API)
cd backend && ../.venv/bin/uvicorn optiqm.api.app:app --reload --port 8000

# Terminal 2 (Frontend Vite)
cd frontend && npm run dev
```

## Menguji Seluruh 43 Modul
```bash
cd backend && ../.venv/bin/python -m pytest -v
```

## Dokumentasi
- [Arsitektur Sistem](docs/ARCHITECTURE.md)
- [Format File Upload](docs/FILE_FORMAT.md)
- [Panduan Menambah Modul Baru](docs/MODULE_GUIDE.md)
- Contoh workbook siap upload: [OptiQM_Sample_10_Modul.xlsx](samples/OptiQM_Sample_10_Modul.xlsx)

## Deploy Online (Netlify + Backend Python)
Karena Netlify hanya menghosting frontend statis, deploy aplikasi web terbagi menjadi dua bagian:

1. **Backend FastAPI (`backend/`)** — deploy ke **Render** (otomatis memakai `render.yaml`), **Railway**, **Fly.io**, atau host Docker mana pun memakai `backend/Dockerfile` dengan perintah:
   ```bash
   uvicorn optiqm.api.app:app --host 0.0.0.0 --port $PORT
   ```
   Pastikan endpoint `/api/health` merespons `{"status": "ok"}`.

2. **Frontend React (`frontend/`) di Netlify** — repo ini sudah menyertakan `netlify.toml` (`base = "frontend"`, `publish = "dist"`).
   - Sambungkan repositori GitHub ke Netlify.
   - Tambahkan **Environment Variable** di dashboard Netlify:
     ```text
     VITE_API_BASE_URL=https://url-backend-anda.onrender.com
     ```
   - Trigger **Deploy site** (atau **Clear cache and deploy site** setelah mengubah environment variable).


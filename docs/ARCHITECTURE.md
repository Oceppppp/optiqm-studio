# Arsitektur OptiQM Studio

OptiQM Studio dirancang menggunakan arsitektur **modular berlapis (layered plugin architecture)** sehingga seluruh 43 modul perhitungan terpisah rapi (rata-rata 80–250 baris per file) dan tidak ada file monolitik.

```
optiqm-studio/
├── backend/
│   ├── optiqm/
│   │   ├── core/        # Kontrak BaseModule, SheetData, ModuleResult, Plugin Registry
│   │   ├── io/          # Parser Excel/CSV/JSON, Auto-Detector modul, Template Writer
│   │   ├── services/    # ImportService, BatchRunner (paralel), ReportService (Excel & PDF)
│   │   ├── api/         # FastAPI app & REST routers
│   │   └── modules/     # 43 sub-package modul independen (@register auto-discovered)
│   └── tests/           # Pytest unit & integration tests (48 test cases)
├── frontend/            # React + TypeScript + Vite + Vanilla CSS Design System
├── desktop/             # pywebview native window launcher & PyInstaller spec
└── .github/workflows/   # CI pytest/build + Release multi-OS (.exe/.app/Linux)
```

## Prinsip Utama
1. **Plugin Auto-Discovery**: Menambah modul baru cukup membuat sub-package baru di `optiqm/modules/<nama>/` dengan dekorator `@register` — otomatis muncul di UI, API, auto-detect, dan laporan.
2. **Isolasi Error pada Batch Run**: Ketika menjalankan banyak modul sekaligus (`POST /api/batch/run`), tiap modul berjalan independen pada `ThreadPoolExecutor`; kegagalan satu modul tidak menggagalkan modul lain.
3. **Format Data & Hasil Seragam**: Semua sumber input (Excel/CSV/JSON/Google Sheets/Editor UI) dikonversi ke `SheetData`, dan seluruh solver mengembalikan `ModuleResult` (`summary`, `tables`, `charts`, `steps`, `interpretation`) sehingga satu komponen UI & generator laporan menangani semua 43 modul.

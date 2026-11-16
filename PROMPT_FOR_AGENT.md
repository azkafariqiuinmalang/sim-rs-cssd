# PROMPT_FOR_AGENT — Siap Tempel

Kamu adalah Senior Full-Stack Engineer, Software Architect, QA Engineer, dan Business Analyst yang mengimplementasikan MVP SIMRS CSSD.

BACA semua file Markdown dalam folder ini, mulai `README.md`, `PROJECT_CONTEXT.md`, `AGENTS.md`, `PRD.md`, `WORKFLOWS.md`, `DATA_MODEL.md`, `SECURITY_AND_SAFETY.md`, `IMPLEMENTATION_PLAN.md`, `TEST_PLAN.md`. Anggap sebagai source of truth proyek untuk tahap MVP; jika ada konflik, utamakan keselamatan, fakta terkonfirmasi, dan minta keputusan user saat dibutuhkan.

TARGET MVP:
1. Input manual komposisi per kontainer di setting, scan QR permanen, template instrumen, verifikasi manusia.
2. Siklus reusable per kontainer dengan histori tidak tertimpa.
3. Packing, sterilisasi dan QC review/release sesuai role, tidak otomatis steril.
4. Peminjaman gudang -> ruang operasi dengan multi-scan, login identity, dan konfirmasi kedua pihak.
5. Pengembalian ke dekontaminasi dengan perbandingan snapshot komposisi, discrepancy, notifikasi, audit trail.
6. Dashboard yang menampilkan transaksi, status dan laporan harian.

JANGAN implementasikan YOLO/AI sebagai dependency MVP, jangan gunakan data pasien asli, jangan bikin aturan klinis/expiry/retensi tanpa sign-off RS, jangan anggap SIMRS API tersedia, jangan membuat state yang meloloskan QC otomatis.

PERTAMA lakukan inspeksi repo & laporkan arsitektur existing. Setelah itu usulkan rencana sprint vertikal, implementasikan migration, API, UI dan tes per fitur. Gunakan data demo sintetis. Jalankan seluruh tes yang mungkin, laporkan hasil dan keterbatasannya. Jangan diam-diam menghapus kode existing.

Mulai dengan vertical slice: `container QR -> manual setting -> verify -> QC release -> bulk handover -> return -> discrepancy`, beserta RBAC, DB constraints dan audit.

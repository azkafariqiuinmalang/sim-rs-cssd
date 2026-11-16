# AGENTS — Panduan AI Coding Agent

## Misi
Implementasikan MVP SIMRS CSSD berorientasi operasional, cepat, aman, dan teruji. Baca `README.md`, `PROJECT_CONTEXT.md`, `PRD.md`, `WORKFLOWS.md`, `DATA_MODEL.md`, `SECURITY_AND_SAFETY.md` sebelum coding.

## Cara bekerja
1. Inspeksi repository & stack yang sudah ada. **Jangan mengganti stack atau menghapus kode pengguna tanpa alasan dan izin.**
2. Susun rencana singkat, cek dependensi, migrasi, UI dan tes yang terdampak.
3. Implementasikan incremental vertical slices; migration + API + UI + test, bukan hanya mockup.
4. Buat seed data sintetis, bukan data pasien asli.
5. Jalankan linter, typecheck, tes, build; laporkan hasil yang benar-benar dijalankan.
6. Catat asumsi dan trade-off di `DECISIONS.md`; taruh kebijakan rumah sakit yang belum diketahui di `OPEN_QUESTIONS.md`.

## Aturan produk wajib
- QR permanen memuat opaque container identifier / URL resolusi aman, **bukan** payload isi instrumen, data pasien, atau token login.
- Satu kontainer bisa banyak siklus; **siklus lama tidak boleh ditimpa**. Tidak boleh dua siklus aktif konflik untuk kontainer sama.
- Setting: input manual diambil dari template master set; petugas wajib menghitung fisik dan memverifikasi. Perubahan setelah verifikasi harus dilog/revisi atau siklus baru sesuai SOP.
- Model pengisian `MANUAL`, dengan tempat untuk `AI_ASSISTED` nanti, tetapi **jangan implementasikan YOLO di MVP**.
- `QC_RELEASED` bukan konsekuensi otomatis dari input, pengemasan atau proses mesin; butuh aksi petugas berwenang & bukti SOP.
- Peminjaman harus **atomic**: tidak bisa double-loan atau kontainer berstatus belum siap, expired, quarantined, atau already borrowed.
- Pisahkan permintaan, persiapan, serah terima, dan penerimaan. Peminjam login + identitas unit; gudang mengonfirmasi serah terima fisik. Dukung banyak QR dalam satu transaksi.
- Pengembalian harus berreferensi ke transaksi keluar, membandingkan jumlah aktual yang diverifikasi dengan snapshot terakhir yang diserahkan, dan mencatat discrepancy.
- Jangan menyalahkan otomatis peminjam terakhir; buat investigasi dan eskalasi ke personel berwenang.
- Jangan menjadikan QR-scan, foto, atau hasil AI sebagai bukti sterilitas atau jumlah fisik yang sudah diverifikasi.
- Audit trail append-only untuk tindakan penting; role-based authorization; timestamp server; validasi backend, bukan hanya frontend.
- Jangan otomatis memutuskan apa yang harus dilakukan terkait retained surgical item, radiologi, atau prosedur pasien: eskalasi sesuai SOP RS.

## Kualitas UI
- Mobile-first; tombol besar; scan cepat; default dari sesi login; multi-scan; hindari mengetik nama dan daftar item berulang.
- Tetap bisa melihat data melalui URL bila kamera perangkat gagal; sediakan prosedur manual fallback berizin.
- Pesan status membedakan `PENDING`, `HANDED_OVER`, `RETURNED`, dan `QC_RELEASED` dengan jelas.
- Hindari pola "simpan = sudah steril".

## Keamanan & kepatuhan
Ikuti `SECURITY_AND_SAFETY.md`; hindari log berisi PII, foto atau nomor MR; gunakan data sintetis; jangan membuka endpoint QR anonim yang membocorkan informasi sensitif.

## Definition of Done
- Kriteria penerimaan `PRD.md` dan skenario `TEST_PLAN.md` lulus.
- Migration reversible dan constraints database diuji.
- Tindakan kritikal memiliki audit entry, role check, dan penanganan error.
- README setup lokal & seed/demo disediakan oleh implementasi.
- Jika ada blocker, laporkan dan jangan diam-diam membuat aturan klinis.

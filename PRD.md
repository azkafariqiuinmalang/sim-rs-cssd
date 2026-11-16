# PRD — Product Requirements Document

## Problem statement
Google Form telah selesai namun menghambat alur ruang operasi yang volume permintaannya tinggi; pada pengembalian, instrumen kurang/tidak lengkap dan sulit ditelusuri. Solusi harus mengurangi input ulang sambil menjaga akuntabilitas.

## Persona dan hak akses

| Role | Hak akses |
|---|---|
| `admin` | Akun, master instrumen, template set, kontainer, konfigurasi, dan log aktivitas. |
| `petugas_cssd` | Setting, sterilisasi, QC, gudang, dekontaminasi, dan riwayat. Keputusan QC memerlukan izin `can_release_qc` per akun. |
| `petugas_unit` | Ajukan peminjaman, lihat status transaksi unit, dan konfirmasi penerimaan sendiri. |
| `supervisor` | Pantau aktivitas, tangani selisih, dan buat laporan. |

## Fitur MVP & acceptance criteria
### FR-01 Master kontainer, set, instrumen
- CRUD terotorisasi master; jenis set bisa mempunyai template instrumen versi tertentu.
- **AC:** detail kontainer menampilkan QR identifier, tipe set, siklus aktif dan histori.

### FR-02 Setting manual per siklus
- Scan QR -> buka halaman kontainer -> pilih template -> input aktual dan kondisi -> periksa fisik -> verifikasi -> simpan snapshot.
- **AC:** data lama tetap ada; hanya satu siklus aktif; selisih standar diberi flag dan tidak otomatis approved; verifikasi menyimpan actor & waktu.

### FR-03 Packing, sterilisasi, QC
- State workflow dan catatan petugas; bukti proses sesuai kebijakan yang dikonfirmasi.
- **AC:** hanya petugas CSSD dengan izin QC dapat mencatat keputusan; rejected tidak tersedia di gudang; hasil input manual tidak otomatis merilis.

### FR-04 Peminjaman cepat
- Login, scan satu/lebih QR dalam satu sesi, persiapkan transaksi, gudang mengonfirmasi penyerahan.
- **AC:** tidak mengetik ulang isi set; identitas petugas dari login; hanya kontainer `AVAILABLE` dan released yang dapat diserahkan; concurrency mencegah pinjam ganda.

### FR-05 Pengembalian
- Scan QR/lookup transaksi aktif -> daftar set & snapshot komposisi -> input jumlah aktual -> konfirmasi penerimaan petugas dekontaminasi.
- **AC:** selalu tertaut ke loan/handover; jumlah tak sesuai membuat discrepancy; tidak boleh otomatis dianggap lengkap; tidak bisa return dua kali tanpa alasan terotorisasi.

### FR-06 Penelusuran dan notifikasi
- Setiap selisih membuat case dengan unit dan titik handover terkait, status investigasi, tindakan, bukti, penanggung jawab.
- **AC:** peminjaman terakhir dicatat sebagai informasi klarifikasi, bukan kesimpulan kesalahan; hanya peran berwenang menutup case dengan alasan.

### FR-07 Dashboard
- Antrean gudang, stok set tersedia, dipinjam, tertunda QC, kasus selisih, frekuensi peminjaman per unit, laporan harian.
- **AC:** angka dashboard dapat ditelusuri ke transaksi sumber; filter tanggal dan unit.

### FR-08 Audit & akses
- Role-based access, audit trail, server timestamp, error handling, idempotency.
- **AC:** pengguna tanpa role tidak dapat mengubah QC, transaksi lain, atau histori; audit tak bisa diedit melalui UI.

## Nonfunctional
- Responsif mobile/tablet; jelas dan minim klik; gracefully handle kamera/scan gagal.
- Database transactional & constraint concurrency untuk transfer.
- Backup dan restore teruji sebelum produksi.
- Semua waktu disimpan UTC, ditampilkan lokal Asia/Jakarta.
- Penggunaan offline bukan MVP kecuali ditentukan RS; aplikasi harus memperlihatkan kegagalan jaringan dengan jelas.

## Ukuran keberhasilan (target ditetapkan setelah baseline)
Waktu peminjaman per transaksi; klik/input per transaksi; rate scan berhasil; persentase serah terima lengkap; jumlah discrepancy dan waktu resolusi; tingkat pemakaian sistem; kesalahan status.

## Tidak termasuk MVP
YOLO/CV, segmentasi otomatis, chatbot, rekomendasi tindakan klinis, integrasi SIMRS produksi, aturan expiry/retensi hardcoded.

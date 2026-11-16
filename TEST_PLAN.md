# TEST_PLAN — Acceptance & Safety Scenarios

## Unit & integration
- `create_cycle`: kontainer punya sejarah 2 siklus; siklus lama tetap bisa dibaca, composition snapshot tidak berubah.
- `verify_setting`: tanpa login/role ditolak; perubahan angka tercatat; mismatch tidak otomatis menjadi approved.
- `qc_release`: akun tanpa izin QC mendapat 403 saat mengirim keputusan; QC reject -> tidak tampil AVAILABLE.
- `handover`: scan released valid -> success; kontainer expired/rejected/quarantined/borrowed -> reject.
- `concurrent_handover`: dua permintaan bersamaan untuk kontainer sama -> tepat satu berhasil.
- `double_submit`: idempotency key sama -> tidak duplikasi transaksi.
- `bulk_handover`: kegagalan satu set tidak menghasilkan status setengah-terpinjam secara diam-diam.
- `return`: resolve loan dan cycle yang benar, bukan cycle terbaru yang baru dibuat.
- `discrepancy`: expected 2, received 1 -> case OPEN, audit, notifikasi; tidak auto accusatory.
- `no_discrepancy`: expected==received -> tetap wajib konfirmasi fisik dan pemrosesan ulang.
- `audit`: semua perubahan kritis mempunyai actor, timestamp server, referensi, reason, tamper-resistant.
- `authorization`: petugas OK tidak dapat QC release; petugas lain tidak bisa ubah verifikasi yang sudah final.
- `privacy`: QR anonim tidak memuat identitas pasien, tidak dapat membaca histori rinci tanpa login.

## End-to-end demo
1. Setup master Set SC dengan 3 instrumen fiktif; kontainer C-001.
2. Setting scan C-001, pilih template, input angka & verify.
3. Catat packing, sterilization batch, QC release.
4. Gudang siapkan; peminjam scan C-001 + C-002 dalam batch; gudang konfirmasi.
5. Cek stok/riwayat berubah; loan muncul di unit peminjam.
6. Return C-001, sengaja kurangi satu instrumen, buat discrepancy & notifikasi.
7. Supervisor melihat audit dan menyelesaikan berdasarkan evidence demo.
8. C-001 menjalani dekontaminasi lalu siklus berikut; sejarah lama tetap tersedia.

## Usability pilot
Minta petugas simulasi tugas asli dengan data sintetis; catat jumlah klik, input berulang, kesalahan scan, durasi peminjaman & pengembalian, kemampuan menemukan riwayat kehilangan. Bandingkan baseline Google Form.

## Nonfunctional
Uji mobile viewport, kamera permission denied, network timeout, role expiry, retry idempotent, backup/restore, rate limiting, monitoring error, escape user inputs.

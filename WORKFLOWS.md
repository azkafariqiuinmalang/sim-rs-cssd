# WORKFLOWS — State Machine dan Happy/Exception Paths

## A. Setting ke gudang
1. Petugas setting login di perangkat area bersih.
2. Scan QR permanen -> backend resolve `container_id`.
3. Pastikan tidak ada siklus aktif lain yang menghalangi. Buat `container_cycle` baru; pilih `set_template_version`.
4. Tampilkan daftar komposisi standar; petugas input jumlah fisik, kondisi dan catatan selisih. Default angka template adalah panduan, **bukan hasil hitung**.
5. Petugas menandai pemeriksaan selesai dan verifikasi; simpan `cycle_instruments` snapshot + audit. Perubahan berikutnya memerlukan prosedur revisi berjejak/otorisasi.
6. Packing lalu catat proses sterilisasi. Pemeriksaan QC dilakukan menurut SOP, bukan ditentukan software.
7. Petugas CSSD dengan izin QC mengisi keputusan: release atau reject/quarantine. Hanya `QC_RELEASED` berhak masuk stok tersedia.

## B. Peminjaman cepat (bulk)
1. Peminjam login; unit terisi dari akun/sesi.
2. Scan banyak QR ke satu keranjang; sistem menampilkan status/jenis set (tanpa mengharuskan membuka kontainer).
3. Tombol ajukan / siapkan; transaksi `REQUESTED` atau `PICKING`.
4. Gudang memvalidasi kontainer fisik, identitas penerima dan status. Konfirmasi handover secara atomik -> `HANDED_OVER` dan seluruh kontainer terkait `BORROWED`.
5. Sistem menyimpan `loan` + `loan_items` dengan `container_id`, `cycle_id`, snapshot summary/reference, petugas serah, petugas terima, unit, waktu.
6. Jika salah satu kontainer tidak siap, tampilkan secara eksplisit; jangan silently handover partial tanpa persetujuan alur.

## C. Pengembalian
1. Petugas/area penerimaan scan kontainer atau pilih loan yang masih aktif.
2. Sistem menampilkan komposisi dari `cycle_instruments` pada `cycle_id` yang dipinjam.
3. Petugas menghitung ulang alat yang diterima secara fisik, menginput jumlah aktual & kondisi.
4. Petugas dekontaminasi konfirmasi penerimaan, scan/identitas actor tercatat.
5. Jika ada perbedaan: buat `discrepancy_case` + detail per instrumen, notifikasi sesuai izin; kontainer/set menuju status ditahan/penanganan sesuai SOP.
6. Jika lengkap pun bukan otomatis steril; harus melalui dekontaminasi -> setting -> siklus baru.

## D. Penanganan selisih
`OPEN -> INVESTIGATING -> (FOUND | RECONCILED | ESCALATED) -> RESOLVED` (status final dan escalation disesuaikan SOP). Semua pembaruan append-only audit; pencarian melibatkan penanggung jawab bukan tuduhan otomatis. Missing item yang mungkin masih dalam pasien mengikuti eskalasi keselamatan segera di luar alur menunggu aplikasi.

## E. State model konseptual
`DRAFT_SETTING -> VERIFIED_SETTING -> PACKAGED -> STERILIZATION_IN_PROGRESS -> STERILIZATION_COMPLETE -> QC_PENDING -> QC_RELEASED -> AVAILABLE -> RESERVED/PICKING -> HANDED_OVER/BORROWED -> RETURN_PENDING -> DIRTY_RECEIVED -> DECONTAMINATION -> NEW_CYCLE`

Cabang: `REJECTED`, `QUARANTINED`, `DISCREPANCY_OPEN`, `CANCELLED`, `EXPIRED` (bukan semua dalam satu enum; pisah lifecycle/availability bila diperlukan). Untuk konfigurasi status sesungguhnya, validasi ke staf CSSD.

## Aturan invariants
- Scan tidak mengubah status otomatis.
- Status `BORROWED` hanya setelah handover yang sah.
- Tidak ada dua handover aktif untuk kontainer/siklus yang sama.
- `QC_RELEASED` tidak terjadi tanpa tindakan berwenang.
- Semua perubahan jumlah tercatat bersama actor & alasan.
- Tidak dapat meminjam kontainer yang expired/rejected/quarantined, sedang dipinjam, atau belum QC release.
- Setiap siklus menyimpan snapshot independen dari template yang suatu hari bisa berubah.

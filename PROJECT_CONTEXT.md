# PROJECT_CONTEXT — SIMRS Khusus CSSD

## 1. Konteks
Klien: lingkungan CSSD RSUD Grati, berdasarkan catatan diskusi yang dibagikan pengguna dan percakapan lanjutan. Dokumen **bukan SOP resmi**, melainkan catatan kebutuhan awal; seluruh keputusan yang memengaruhi keselamatan memerlukan validasi oleh rumah sakit.

## 2. Fakta dari catatan klien
- Proses mencakup dekontaminasi, setting/packing, sterilisasi, pemeriksaan kualitas, gudang steril, distribusi, dan pengembalian.
- Set operasi (contoh: Set SC) dapat memiliki komposisi khas rumah sakit. Serah terima harus memeriksa jenis dan jumlah item.
- Kontainer yang sudah disterilkan tidak dibuka hanya untuk mengecek isi saat peminjaman.
- Keluhan operasional: pengembalian instrumen tidak lengkap, checklist fisik sering tidak dilakukan, instrumen bisa terbawa laundry/terbuang, dan proses selanjutnya terhambat.
- Petugas keberatan pada input panjang/berulang; ruang operasi memerlukan layanan cepat.
- Catatan awal meminta dua Google Form (peminjaman dan pengembalian), QR akses form, foto, laporan harian, serta demo sebelum pengajuan ke direktur.

## 3. Fakta tambahan dari pengguna (percakapan)
- Google Form telah selesai dibuat, tetapi peminjaman di ruang operasi terasa berat karena frekuensi dan volume permintaan.
- User memilih **mengganti Computer Vision/YOLO dengan input manual oleh petugas setting** untuk MVP karena data anotasi belum siap.
- Sebelum isi alat masuk kontainer, petugas setting **scan QR kontainer permanen**, input/konfirmasi jenis serta jumlah alat, dan menyimpan catatan komposisi untuk siklus saat itu.
- QR yang sama digunakan gudang dan peminjam untuk melihat isi tercatat tanpa membuka kontainer.
- Pengembalian memerlukan pemeriksaan kelengkapan dan kemampuan menelusuri unit/petugas yang terakhir menerima set.

## 4. Interpretasi desain / hipotesis (belum disetujui RS)
- Ada master set, master instrumen, kontainer fisik permanen, dan banyak siklus per kontainer.
- Untuk efisiensi, komposisi standar ditampilkan sebagai draft yang HARUS dihitung dan diverifikasi fisik; jangan isi ulang dari nol.
- Peminjaman dilakukan multi-scan, akun login otomatis menyediakan identitas petugas, lalu ada konfirmasi serah-terima dari gudang.
- Scan QR mencatat aktivitas apabila transaksi dikonfirmasi, bukan bukti otomatis lokasi fisik/sterilitas.
- Hasil setting tidak mengubah status menjadi steril/tersedia; QC release oleh petugas berwenang menjadi gerbang distribusi.

## 5. Tujuan utama
1. Mengurangi ketikan dan langkah peminjaman di ruang operasi.
2. Mempercepat penyusunan catatan isi kontainer tanpa membuka set steril.
3. Menyimpan riwayat komposisi **per siklus** tanpa menimpa histori lama.
4. Mendeteksi selisih saat alat dikembalikan; membuat kasus dan menelusuri titik serah terima.
5. Menyediakan pelaporan dan audit yang bisa dipakai demo.

## 6. Out of scope MVP
- YOLO/CV otomatis, object counting, auto-retraining.
- AI Agent/LLM untuk keputusan klinis atau release sterilisasi.
- Integrasi SIMRS/SITS produksi tanpa spesifikasi dan izin.
- Tracking GPS/RFID instrumen individual, prediksi kebutuhan otomatis.
- Penyimpanan rekam medis pasien sebenarnya pada demo.

## 7. Definisi istilah
- **Kontainer:** wadah fisik dengan QR permanen; berulang kali digunakan.
- **Siklus:** satu episode persiapan/pengemasan/pemrosesan yang spesifik terhadap kontainer dan snapshot komposisi.
- **Set:** jenis paket (misal Set SC), punya template komposisi versi tertentu.
- **Snapshot komposisi:** jenis dan jumlah instrumen yang diverifikasi untuk satu siklus, tidak ditimpa siklus berikutnya.
- **Discrepancy:** perbedaan data yang memerlukan pemeriksaan, bukan otomatis bukti kehilangan atau kesalahan petugas.

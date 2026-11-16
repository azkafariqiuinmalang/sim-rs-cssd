# DECISIONS — Architecture Decision Records (draft)

## ADR-001 — Manual-first, AI-later
**Keputusan:** MVP input instrumen oleh petugas setting, bukan YOLO. **Alasan:** data beranotasi belum siap, proses aktual sudah memiliki checkpoint setting. **Konsekuensi:** fitur verifikasi fisik wajib; sediakan hook AI nanti. **Sumber:** keputusan pengguna.

## ADR-002 — QR permanen hanya pointer
**Keputusan:** kontainer memiliki satu QR identifier yang tetap; konten komposisi dibaca dari database per siklus. **Alasan:** kontainer reusable, isi berubah. **Konsekuensi:** perlu koneksi/strategi fallback & autentikasi. **Status:** rancangan yang disetujui secara konsep pengguna.

## ADR-003 — Immutable cycle snapshot
**Keputusan:** setiap reuse menciptakan siklus baru, riwayat tak di-overwrite. **Alasan:** audit & perbandingan saat return. **Status:** rekomendasi kuat.

## ADR-004 — Separasi QC dan inventory
**Keputusan:** input setting tidak mengubah stok siap-pinjam; release eksplisit oleh petugas dengan izin QC per akun. **Alasan:** keselamatan. **Status:** perlu validasi workflow detail RS.

## ADR-005 — Bulk scan + dua pihak handover
**Keputusan:** peminjam dapat scan multi-kontainer, gudang mengonfirmasi transfer fisik. **Alasan:** mengurangi friksi sekaligus akuntabilitas. **Status:** desain usulan, uji dengan staf.

## ADR-006 — Discrepancy tidak otomatis berarti hilang
**Keputusan:** mismatch menjadi kasus investigasi; record unit/petugas sebelumnya sebagai titik penelusuran. **Alasan:** data tidak membuktikan penyebab. **Status:** wajib.

## ADR-007 — Tidak mengubah SOP lokal lewat asumsi
**Keputusan:** konfigurasi retensi, expiry, dan detail bukti sterilisasi bukan konstanta hardcoded. **Alasan:** catatan wawancara tidak setara SOP. **Status:** wajib.

## ADR-008 — Tech stack non-preskriptif
**Keputusan:** contoh React/FastAPI/PostgreSQL hanya usulan. **Alasan:** repo existing belum ditinjau. Agent mengadopsi stack existing kecuali ada keputusan eksplisit.

## ADR-009 - Supabase PostgreSQL
**Keputusan:** Flask mengakses PostgreSQL Supabase dari backend lewat `CSSD_DATABASE_URL`. Tabel CSSD berada dalam skema privat `cssd_app`. Akun demo dan RBAC tetap ditangani Flask.
**Alasan:** Konfirmasi serah terima, audit, dan pengembalian membutuhkan satu transaksi database. Koneksi Session pooler mendukung penggunaan konfigurasi sesi.
**Konsekuensi:** Transaksi perubahan data mengambil advisory lock untuk menserialisasi penulisan selama demo. Pembacaan tetap dapat berjalan bersamaan. Uji beban dan hak akses role database khusus diperlukan sebelum pilot. SQLite tetap tersedia untuk membuka data lokal sebelumnya.

## ADR-010 - Empat role dan izin QC per akun
**Keputusan:** Petugas CSSD mengakses semua modul operasional melalui satu akun pribadi. Admin mengatur izin untuk keputusan QC. Petugas unit terbatas pada transaksi unitnya dan supervisor menangani kasus selisih.
**Migrasi:** Pengguna dengan role QC lama mewarisi izin keputusan QC. Role operasional CSSD lainnya digabung. Audit lama memakai username dari identitas akun yang dirujuk, sedangkan audit baru menyimpan snapshot username.
**Validasi RS:** Rumah sakit menetapkan petugas yang berwenang mengambil keputusan QC serta bukti yang dibutuhkan.

## ADR-011 - Demo login per aktor
Satu formulir login memverifikasi akun individual. Role, unit, dan izin QC dibaca dari database. Panduan akun hanya tampil saat `CSSD_DEMO_GUIDE=true` dan hanya mengisi username. Setiap akun sintetis pada database demo baru menerima sandi acak sendiri. Akun pada database yang sudah diinisialisasi tetap memakai kredensial yang tersimpan.

## ADR-012 - Peminjaman dari stok atau QR
Petugas unit bisa memilih stok yang memenuhi syarat atau menambahkan pilihan lewat scan dan kode label. Keranjang memakai ID QR yang sama untuk mencegah pilihan ganda. Ketersediaan diperiksa ulang saat pengajuan dan serah terima. Antrean Gudang hanya menampilkan permintaan yang masih perlu disiapkan atau diserahkan.

Formulir menampilkan set kontainer dan alat satuan lewat filter jenis. Pilihan keduanya tetap masuk ke satu pengajuan dengan jumlah per jenis di ringkasan. Kemasan yang berisi tepat satu instrumen pada snapshot siklus masuk ke kategori alat satuan. Hasil scan mengikuti kategori yang sama dengan katalog.

## ADR-013 - Bukti pengembalian per item pinjaman
Bukti membuka snapshot dari siklus yang diserahkan dan hasil hitung fisik dari rekaman pengembalian. Petugas CSSD, admin, dan supervisor dapat membuka bukti. Riwayat investigasi hanya tersedia bagi supervisor dan dibaca dari audit append-only. Catatan kondisi ditampilkan di bukti. Pembuatan kasus masih dipicu oleh selisih jumlah karena penanganan kondisi fisik perlu validasi RS.

## ADR-015 - Permintaan berdasarkan kebutuhan dan pengembalian

`loan_needs` menyimpan jenis, nama saat diajukan, dan jumlah yang diminta. `loan_items` menyimpan kontainer dan siklus fisik yang dipilih CSSD. Batas waktu kebutuhan WIB diterima dari Unit dan disimpan dalam UTC. Set standar dicocokkan berdasarkan nama template, alat satuan berdasarkan instrumen pada kemasan, dan set khusus berdasarkan komposisi terverifikasi. Satu permintaan set khusus berisi komposisi untuk satu kontainer. Alokasi dapat diganti sebelum serah terima. Stok diperiksa kembali saat konfirmasi serah terima.

Checklist pengembalian mencatat pilihan jumlah sesuai atau jumlah aktual per instrumen setelah pemeriksaan fisik. Jumlah sesuai diturunkan dari snapshot saat diserahkan. Catatan kondisi tetap terpisah dan selisih jumlah mengikuti alur investigasi yang ada.

## ADR-014 - Antarmuka operasional SteriTrack

Setting Alat menampilkan kontainer yang diterima kembali, tertahan karena selisih, dan siap disetting setelah dekontaminasi. Petugas CSSD dapat menyimpan komposisi khusus dari katalog instrumen saat siklus masih draf. Susunan disimpan sebagai versi template yang dirujuk siklus tersebut. Template standar kontainer, QR, dan snapshot siklus sebelumnya tetap tersimpan. Komposisi khusus mengikuti verifikasi fisik, pengemasan, pencatatan sterilisasi, dan keputusan QC seperti template standar.

Gunakan tampilan terang dengan hijau yang diturunkan dari header SteriTrack lama. Navigasi mengikuti otorisasi halaman yang sudah berlaku. Instrumen, stok, status, pinjaman, dan kasus tetap berasal dari transaksi di aplikasi. Font DM Sans dan Instrument Sans disajikan secara lokal. Ringkasan petugas unit menghitung pinjaman dari unit tersebut.

| Pemeriksaan desain | Hasil | Bukti |
| --- | --- | --- |
| Palet, gradien, tipografi, dan ritme layout | PASS | `cssd/static/cssd.css` memuat sistem warna hijau, dua keluarga font, skala radius, dan kolom sesuai isi. |
| Kontras teks dan indikator fokus | PASS | Pemeriksaan pasangan utama menunjukkan kontras minimum 5,72:1 untuk fokus dan 5,85:1 untuk teks sekunder. |
| Navigasi, tindakan, dan landmark | PASS | `base.html`, `navigation.html` dan template fitur memakai landmark, tautan, tombol, dan kontrol HTML. |
| Form, alt QR, fokus, dan status | PASS | `login.html`, `new_loan.html`, `forms.html` dan `container.html` memuat label, pesan validasi, alt QR, serta status dalam teks. |
| Modal, combobox kustom, dan tombol ikon tanpa teks | N-A | Layar yang diperbarui memakai kontrol HTML bawaan dan label yang terlihat. |
| Transisi, gerak, dan sumber data | PASS | Transisi 130 ms dengan reduced motion. Dashboard dirender Flask per permintaan. Keamanan login dan audit diuji oleh `tests/test_workflow.py`. |
| Data simulasi dan teks | PASS | Halaman menandai data sintetis. Angka dihitung dari baris database. NO-PROOF untuk klaim penggunaan rumah sakit. |
| Pemeriksaan pola visual | PASS | Login dua bagian, tabel kontainer, dan daftar transaksi mengikuti kebutuhan masing-masing peran. Tidak ditemukan pola P0 atau HIGH pada layar yang diperbarui. |

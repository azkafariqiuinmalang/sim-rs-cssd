# SIMRS CSSD — Agent Starter Kit

**Status:** Draft kebutuhan produk & panduan implementasi, 14 November 2026. **Bahasa:** Indonesia. **Tujuan:** berikan folder ini ke AI coding agent sebelum mengimplementasikan aplikasi.

## Menjalankan demo dengan Supabase

Gunakan proyek Supabase pengembangan dengan data sintetis. Dari dashboard Supabase, pilih **Connect > Session pooler** dan salin URL PostgreSQL. Gunakan sandi database proyek. Karakter khusus pada sandi perlu di-URL-encode. **Direct connection** juga bisa dipakai jika jaringan mendukungnya.

Flask membaca URL dari variabel `CSSD_DATABASE_URL` pada terminal yang sama. Simpan URL itu di lingkungan backend. Skema `cssd_app` dibuat lewat perintah migrasi dan tidak perlu ditambahkan ke daftar skema yang terekspos Data API. Proyek Supabase cloud dapat diakses langsung dari Flask. Jika sudah menjalankan stack Supabase lokal melalui CLI, gunakan **Database URL** dari `supabase status`.

Jalankan dari folder yang berisi direktori `cssd`.

### Command Prompt (CMD)

```bat
python -m pip install -r requirements-supabase.txt
set "CSSD_DATABASE_URL=POSTGRESQL_URL_DARI_SUPABASE"
for /f %K in ('python -c "import secrets; print(secrets.token_hex(32))"') do @set "CSSD_SECRET_KEY=%K"
set "CSSD_DEMO_GUIDE=true"
python -m flask --app cssd init-demo
python -m flask --app cssd run
```

### PowerShell

```powershell
python -m pip install -r requirements-supabase.txt
$env:CSSD_DATABASE_URL = 'POSTGRESQL_URL_DARI_SUPABASE'
$env:CSSD_SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
$env:CSSD_DEMO_GUIDE = 'true'
python -m flask --app cssd init-demo
python -m flask --app cssd run
```

Ganti `POSTGRESQL_URL_DARI_SUPABASE` dengan URL PostgreSQL. Setelah membuka terminal baru, atur kembali `CSSD_DATABASE_URL` dan `CSSD_SECRET_KEY` sebelum menjalankan Flask.

Jalankan `init-demo` sekali per database. Simpan sandi yang ditampilkan untuk tiap akun, lalu buka [SteriTrack CSSD](http://127.0.0.1:5000). Aktifkan `CSSD_DEMO_GUIDE=true` pada demo sintetis untuk menampilkan pilihan username di halaman masuk. Memilih kartu mengisi username. Sandi tetap dimasukkan dari terminal.

`init-demo` menerapkan migrasi sebelum memasukkan akun dan contoh data. Untuk skema kosong, jalankan `python -m flask --app cssd migrate-db`. Koneksi cloud memakai TLS. URL dengan `sslmode=verify-full` dan sertifikat yang dikonfigurasi juga didukung.

### Login email dengan Supabase Auth

Gunakan proyek pengembangan SteriTrack yang sama untuk database dan Authentication. Terapkan skema dengan `python -m flask --app cssd migrate-db`. Apabila proyek belum punya data demo, gunakan `init-demo` untuk mengisi profil dan kontainer sintetis. Pada **Authentication > Users > Add user > Create new user** buat akun di bawah dengan sandi acak berbeda per akun. Untuk alamat demo ini, gunakan opsi konfirmasi email otomatis.

| Email demo | Profil SteriTrack | Akses |
|---|---|---|
| `admin@steritrack.example.com` | `admin` | Admin Sistem |
| `setting@steritrack.example.com` | `setting` | Petugas CSSD |
| `ok@steritrack.example.com` | `ok` | Petugas Unit, OK Demo A |
| `supervisor@steritrack.example.com` | `supervisor` | Supervisor CSSD |
| `qc@steritrack.example.com` | `qc` | Petugas CSSD dengan izin QC |
| `ok2@steritrack.example.com` | `ok2` | Petugas Unit, OK Demo B |

Setelah keenam akun terbentuk, jalankan SQL berikut di **SQL Editor** pada proyek yang sama. Pemeriksaan dalam transaksi memastikan seluruh akun dan profil cocok sebelum dihubungkan. Role, unit, dan izin QC tetap dibaca dari profil internal.

```sql
DO $$
DECLARE
    linked integer;
BEGIN
    UPDATE cssd_app.users AS profile
    SET auth_user_id = identity.id
    FROM auth.users AS identity
    WHERE profile.username IN ('admin', 'setting', 'ok', 'supervisor', 'qc', 'ok2')
      AND lower(identity.email) = profile.username || '@steritrack.example.com'
      AND identity.email_confirmed_at IS NOT NULL
      AND (profile.auth_user_id IS NULL OR profile.auth_user_id = identity.id);
    GET DIAGNOSTICS linked = ROW_COUNT;
    IF linked <> 6 THEN
        RAISE EXCEPTION 'Diperlukan enam akun demo terkonfirmasi dan profil SteriTrack yang sesuai';
    END IF;
END $$;
```

Atur URL proyek dan **Publishable key** di backend. Di CMD, dengan `CSSD_DATABASE_URL` dan `CSSD_SECRET_KEY` sudah terpasang:

```bat
set "CSSD_SUPABASE_URL=https://PROJECT_REF.supabase.co"
set "CSSD_SUPABASE_PUBLISHABLE_KEY=sb_publishable_GANTI_DENGAN_KEY_PROYEK"
set "CSSD_DEMO_GUIDE=true"
python -m flask --app cssd run
```

Login memakai email dan sandi dari Authentication. Supabase memverifikasi sandi, lalu SteriTrack memetakan UUID Auth ke akun internal. Sesi SteriTrack berakhir paling lama satu jam setelah login atau sesuai masa berlaku token yang lebih singkat. Pada demo lokal tanpa pengaturan Supabase Auth, formulir memakai username.

### Upgrade database demo yang sudah berisi akun

Hentikan Flask, lalu jalankan perintah berikut dari terminal yang sudah memuat konfigurasi database dan secret key. Setelah migrasi selesai, jalankan server kembali.

```bat
python -m flask --app cssd migrate-db
python -m flask --app cssd run
```

Migrasi 002 mempertahankan akun, unit, sandi, ID, dan histori. Login dengan akun lama seperti `setting`; role operasionalnya kini `petugas_cssd`. Akun dengan role QC lama mewarisi izin keputusan QC. Admin dapat membuat akun pribadi dan mengatur izin tersebut dari **Akun petugas**. **Log aktivitas** menampilkan perubahan sesuai filter petugas, modul, kontainer, dan tanggal WIB.

Pada rollback skema 002, beberapa role lama CSSD sudah digabung dan dikembalikan ke `SETTING`, atau ke `QC` apabila akun berizin. Simpan backup sebelum upgrade apabila pemulihan pemetaan persis diperlukan.

### Demo SQLite dengan .env lokal

Petugas Unit dapat mengajukan set kontainer dan alat satuan dalam satu transaksi. Untuk menyiapkan stok alat satuan, Admin membuat template berisi satu alat dengan jumlah satu dan mendaftarkan satu kode kontainer per kemasan. Kemasan muncul di katalog setelah siklusnya mendapat keputusan rilis dari QC. Pemilihan jumlah mengambil kode dari kemasan yang tersedia, dan Gudang memeriksa ketersediaan kembali saat serah terima.

Jika folder ini sudah berisi `.env` dan `instance/demo-aktor.sqlite3`, buka terminal baru di folder yang berisi direktori `cssd`, lalu jalankan:

```bat
python -m venv --system-site-packages .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m flask run
```

Setelah dependensi terpasang, cukup jalankan perintah terakhir. Buka [Demo SteriTrack](http://127.0.0.1:5001). Konfigurasi mengarahkan Flask ke database demo yang sudah terisi. Masuk dengan username dan sandi demo yang sudah diberikan. Flask memprioritaskan variabel dari terminal, jadi gunakan terminal baru bila sebelumnya terhubung ke database lain.

Jika `.env` belum tersedia, buat di folder yang sama. Ganti placeholder dengan nilai acak dari `python -c "import secrets; print(secrets.token_hex(32))"`.

```dotenv
FLASK_APP=cssd
FLASK_RUN_PORT=5001
CSSD_DATABASE=instance/demo-aktor.sqlite3
CSSD_DEMO_GUIDE=true
CSSD_SECRET_KEY=GANTI_DENGAN_NILAI_ACAK
```

Jalankan `.venv\Scripts\python.exe -m flask init-demo` hanya jika file database yang dipilih masih baru. Tanpa `CSSD_DATABASE_URL` dan `CSSD_DATABASE`, Flask memakai database default `instance/demo.sqlite3`. Label QR mengikuti data kontainer di database asal.

### Bandingkan akses empat aktor

| Akun | Role | Yang dapat dicoba |
|---|---|---|
| `admin` | `admin` | Buka **Akun petugas**, **Master data**, atau **Log aktivitas**. |
| `setting` | `petugas_cssd` | Buka **Setting Alat** atau pindah ke Sterilisasi, QC, Gudang, Dekontaminasi, dan Riwayat. |
| `ok` | `petugas_unit` | Lihat stok tersedia, ajukan peminjaman dari OK Demo A, dan konfirmasi penerimaan. |
| `supervisor` | `supervisor` | Buka **Notifikasi selisih**, **Laporan**, atau **Log aktivitas**. |
| `qc` | `petugas_cssd` dengan izin QC | Bandingkan formulir keputusan QC dengan akses baca akun `setting`. |
| `ok2` | `petugas_unit` dari unit lain | Bandingkan transaksi OK Demo B dengan OK Demo A. |

Gunakan **Keluar** sebelum beralih akun. Untuk mencoba satu alur lengkap dengan data sintetis:

1. **`setting`** membuka **Setting Alat → C-001**, memulai siklus, dan mengisi hitungan **Klem Hemostat Mosquito Lurus = 2**, **Pinset Anatomi = 1**, dan **Gunting Metzenbaum Lengkung = 1**. Komposisi ini untuk simulasi. Verifikasi, catat packing, lalu catat proses batch simulasi sampai selesai.
2. **`qc`** membuka **Quality Control → C-001**, memilih **Rilis ke gudang**, dan mengisi referensi bukti simulasi. Setelah itu, kontainer muncul di daftar tersedia akun unit.
3. **`ok`** membuka **Ajukan peminjaman**, mencentang C-001 di stok, lalu mengirim permintaan. **`setting`** membuka **Gudang**, memilih permintaan di antrean, dan mencatat penyerahan kepada akun `ok`. **`ok`** membuka transaksi unitnya lalu mengonfirmasi penerimaan.
4. **`setting`** membuka **Dekontaminasi → C-001** dan mengisi jumlah kembali **1 klem, 1 pinset, dan 1 gunting**. **`supervisor`** membuka kasus selisih yang muncul, lalu **`admin`** membuka **Log aktivitas** dan memfilter `C-001` untuk memeriksa jejak tiap akun.

Untuk database demo yang sudah terisi, pakai akun dan sandi yang ada. Untuk memulai ulang skenario di SQLite terpisah, dari CMD gunakan blok di bawah. Pilih nama file baru pada `CSSD_DATABASE` jika `instance/demo-aktor.sqlite3` sudah berisi akun.

```bat
set "CSSD_DATABASE_URL="
set "CSSD_DATABASE=instance/demo-aktor.sqlite3"
set "CSSD_DEMO_GUIDE=true"
for /f %K in ('python -c "import secrets; print(secrets.token_hex(32))"') do @set "CSSD_SECRET_KEY=%K"
python -m flask --app cssd init-demo
python -m flask --app cssd run --port 5001
```

Buka [SteriTrack CSSD · Demo Aktor](http://127.0.0.1:5001).

### Unit REKAP CSSD RSUD Grati

Untuk membuat basis data demo baru dengan katalog RSUD Grati, jalankan `python -m flask --app cssd init-demo --grati-inventory` pada basis data kosong. Opsi ini menyiapkan set bedah, set nonbedah, kemasan alat satuan, dan beberapa kontainer kosong. Batch, hasil QC, peminjaman, dan jumlah alat adalah data sintetis. Komposisi set contoh disederhanakan untuk simulasi aplikasi dan perlu dicocokkan dengan daftar resmi serta SOP rumah sakit sebelum penggunaan operasional.

Referensi jenis set dan nama instrumen berasal dari [Katalog instrumen IFRC/ICRC](https://itemscatalogue.redcross.int/health--3/surgical-instruments--24/surgical-instrument-sets--110.aspx), [Katalog perangkat medis MSF](https://www.msf.org/sites/default/files/2022-02/MSF-Medical%20devices-2021.pdf), dan [rujukan set bedah PAHO](https://iris.paho.org/handle/10665.2/65763).

Inisialisasi demo baru menyertakan 16 unit sesuai daftar REKAP CSSD. Untuk database yang sudah terisi, jalankan `python -m flask --app cssd seed-grati-units` dengan konfigurasi database yang dipilih. Daftar unit dapat dilihat di **Akun petugas → Buat akun pribadi → Unit** pada demo lokal dan di filter **Unit** pada **Laporan**. Penambahan unit mempertahankan penempatan akun dan referensi transaksi yang sudah tercatat.

### Ajukan kebutuhan dan telusuri pengembalian

Untuk permintaan berdasarkan nama, buka **Ajukan peminjaman**, isi jumlah set atau alat, dan bila perlu tentukan waktu dibutuhkan dalam WIB. Untuk set dengan susunan tersendiri, gunakan **Susun set khusus**. Di **Gudang**, CSSD memilih **Mulai persiapan**. Untuk set khusus, **Mulai setting sesuai permintaan** membuka siklus draf dari jumlah instrumen yang diajukan. Setelah kemasan tersedia, CSSD menyimpan pilihan fisik dan mengonfirmasi serah terima.

Saat menerima pengembalian, pilih **Sesuai** atau **Ada selisih** setelah memeriksa setiap instrumen. Isi jumlah aktual jika ada selisih dan konfirmasi pemeriksaan fisik sebelum menyimpan.

### Batch sterilisasi bersama

Setelah migrasi `python -m flask --app cssd migrate-db`, buka **Sterilisasi** sebagai Petugas CSSD, pilih kontainer yang sudah dikemas, isi satu referensi, lalu klik **Mulai batch terpilih**. Dari salah satu anggotanya, **Catat batch selesai** membuka antrean QC untuk semua kontainer. Petugas berwenang mencatat keputusan QC untuk tiap kontainer. Riwayat batch lama tetap terhubung ke siklus asal.

Untuk PostgreSQL, instal `requirements-supabase.txt` dan gunakan koneksi langsung atau pooler mode sesi. `CSSD_DATABASE_POOL_SIZE` mengatur batas koneksi per proses Flask, default 4. Gunakan 0 untuk koneksi langsung per request. Perhitungkan jumlah proses server saat menentukan batas. Lock penulisan global PostgreSQL tetap dipakai sampai pengujian konkurensi database mengonfirmasi alternatif yang aman.

Setelah unit mengonfirmasi penerimaan, Petugas CSSD dapat membuka transaksi dan memilih **Periksa pengembalian** pada kontainer yang masih dipinjam. Sesudah penghitungan fisik disimpan, buka **Bukti pengembalian** dari transaksi untuk melihat jumlah, catatan kondisi, petugas penerima, dan siklus yang terkait. Supervisor dapat membuka kasus selisih untuk menelusuri serah terima, pengembalian, dan catatan investigasi.

### Unduh laporan Excel

Masuk sebagai supervisor, buka **Laporan**, pilih tanggal WIB dan unit, lalu klik **Unduh Excel**. Serah terima ditampilkan berdasarkan waktu penyerahan. Pengembalian dan selisih memakai waktu pengembalian, termasuk pengembalian pinjaman yang diserahkan pada hari sebelumnya. Status transaksi dan kasus mencerminkan kondisi saat laporan diunduh. Ringkasan stok mencakup semua unit dan menunjukkan kondisi saat unduhan dibuat. **Belum Kembali** memuat satu baris per kontainer yang sudah diserahkan dan belum kembali. **Kasus Aktif** memuat satu baris per kasus terbuka atau sedang diinvestigasi. Kedua daftar mengikuti filter unit dan mencakup seluruh tanggal. Jumlah serah terima per unit dihitung untuk tanggal laporan.

### Pengujian

Jalankan `python -m unittest discover -s tests -v`. Untuk ikut menjalankan skenario integrasi PostgreSQL, set `CSSD_TEST_DATABASE_URL` ke **database kosong yang dibuat khusus untuk pengujian**. Tes tersebut menerapkan migrasi dan mengisi data sintetis, lalu meninggalkan skema serta data uji untuk inspeksi. Gunakan database kosong baru untuk pengujian berikutnya.

## Visi
Sistem operasional CSSD yang **cepat bagi peminjam**, **ringan bagi petugas setting**, dan **terlacak saat ada ketidaksesuaian instrumen**. MVP tidak membutuhkan computer vision. Input komposisi set dilakukan petugas setting berdasarkan pemeriksaan fisik, dikaitkan dengan QR permanen kontainer, dan dicatat per siklus.

## Baca dalam urutan ini
1. `PROJECT_CONTEXT.md` — fakta klien vs keputusan rancangan.
2. `AGENTS.md` — instruksi agent, larangan, dan definition of done.
3. `PRD.md` — ruang lingkup fitur dan kriteria penerimaan.
4. `WORKFLOWS.md` — alur setiap aktor, pengecualian, status.
5. `DATA_MODEL.md` — entitas, relasi, constraints.
6. `ARCHITECTURE.md` — pilihan arsitektur dan kontrak API awal.
7. `SECURITY_AND_SAFETY.md` — kontrol operasional, privasi, audit.
8. `IMPLEMENTATION_PLAN.md` — tahapan & backlog.
9. `DECISIONS.md` — keputusan & alasan.
10. `OPEN_QUESTIONS.md` — informasi untuk divalidasi ke RS.
11. `TEST_PLAN.md` — contoh tes end-to-end dan nonfunctional.
12. `PROMPT_FOR_AGENT.md` — prompt siap tempel ke coding agent.

## Batasan
- Google Forms untuk permintaan/pengembalian **sudah pernah diimplementasikan**; bukan diminta dibuat ulang di MVP aplikasi.
- Jangan klaim integrasi SIMRS/SITS sudah tersedia.
- Jangan menganggap aturan sterilisasi, usia simpan, komposisi set, retensi atau prosedur keselamatan tertentu telah disetujui RS bila belum diverifikasi.
- Gunakan **data sintetis** untuk demo; tidak mengunggah data pasien asli ke sistem pengembangan.

## Target demo utama
`Setting scan QR -> input dan verifikasi komposisi -> pengemasan -> pemrosesan sterilisasi -> QC release -> gudang -> peminjaman multi-scan dan serah terima -> pengembalian -> pencocokan jumlah -> discrepancy & audit -> siklus baru.`

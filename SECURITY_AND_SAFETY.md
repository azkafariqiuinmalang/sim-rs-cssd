# SECURITY_AND_SAFETY — Wajib Sebelum Produksi

## Boundary keselamatan
- Aplikasi adalah **pencatatan, traceability dan dukungan verifikasi**, bukan pengganti SOP dekontaminasi/sterilisasi, QC, instrument count operasi, atau keputusan klinis.
- Tidak boleh menyatakan steril/aman hanya dari input manual, indikator tunggal, foto, QR, atau model AI.
- Pemeriksaan jumlah instrumen fisik tetap dilakukan oleh petugas terlatih; ketidaksesuaian terkait operasi mengikuti eskalasi segera sesuai SOP dan petugas berwenang.
- Software tidak boleh mengasumsikan expiry universal 3 bulan atau memilih tindakan terhadap pasien.

## Akses & identitas
- Auth individual, session timeout sesuai kebijakan; jangan memakai satu akun bersama untuk semua petugas.
- Server-side RBAC untuk read/write setiap modul.
- Dua pihak untuk handover: penerima teridentifikasi dan konfirmasi gudang; metode tanda tangan ditetapkan RS.
- Supervisor/admin tidak otomatis diberi akses ke seluruh PII tanpa alasan.

## Privacy dan compliance
- Demo hanya data sintetis.
- Minimisasi data pasien: nama/no MR bukan field wajib MVP; implementasi jika disetujui dengan legal/IT RS.
- Jangan menaruh PII, daftar instrumen atau credential dalam QR.
- HTTPS/TLS, encryption at rest bila didukung infra, access logs, backup terenkripsi, secrets di environment manager.
- Jangan mempublikasikan foto dokumen/pasien; audit metadata bukan dump isi sensitif.
- Kebijakan retensi dari catatan wawancara **5 tahun** perlu konfirmasi jenis dokumen, dasar hukum dan pihak pengesah; jangan auto-delete.
- Hosting/cloud, foto dan data rumah sakit perlu persetujuan tertulis pemilik data/IT RS.

## Audit
Append-only event untuk create/update/verify/release/handover/return/case closure, mencatat actor, waktu server, objek, perubahan penting, dan alasan. UI tidak memberi fitur delete audit.

## Penanganan kegagalan
- Network failure: jangan tampilkan transaksi berhasil sebelum commit server; sediakan retry idempotent.
- QR tak terbaca: fallback pencarian ID dan verifikasi fisik terotorisasi.
- Wrong label / missing QR: karantina/rekonsiliasi menurut SOP; jangan reassign diam-diam.
- Status sync conflict: tolak, refresh dan jelaskan alasan.
- Tidak boleh menyembunyikan discrepancy dengan menekan tombol "selesai".

## Produksi membutuhkan sign-off
Pemilik proses CSSD, petugas OK, pengelola mutu/keselamatan pasien, IT SIMRS, dan otorisasi keamanan/informasi rumah sakit sesuai tata kelola setempat.

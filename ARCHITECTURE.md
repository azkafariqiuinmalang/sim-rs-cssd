# ARCHITECTURE — Konsep Teknis dan Integrasi

## Prinsip
Mobile-first PWA untuk petugas, API transactional, database relasional, storage foto opsional dengan kebijakan RS. **Tetap agnostik terhadap stack:** sebelum menulis kode, agent memeriksa repository pengguna.

## Stack contoh (bukan kewajiban)
- Frontend React/Next.js PWA, kamera QR scanner dengan fallback input ID yang diotorisasi.
- Backend Python FastAPI **atau** TypeScript framework yang sudah digunakan repo.
- PostgreSQL untuk workflow transaksional; object storage privat bila ada dokumen/foto.
- Job queue/outbox untuk notifikasi agar perubahan transaksi dan pengiriman pesan tidak saling menggagalkan.

## Komponen
`UI RBAC -> Auth/API -> Container & Cycle Service -> Setting Service -> Sterilization/QC Service -> Loan/Handover Service -> Return/Discrepancy Service -> PostgreSQL`

Notifikasi dari `outbox` -> worker -> panel pengguna/pesan internal. External SIMRS adapter **nanti** saat interface disetujui.

## QR
- Memuat URL dengan `qr_public_id` opaque: `/c/{opaque-id}`. Bukan konten JSON komposisi.
- Saat dibuka, require login; authorize role sebelum menampilkan data terperinci.
- Data QR kontainer permanen, siklus saat itu di-resolve dari server.
- Label siklus/indikator fisik mengikuti SOP dan bukan digantikan QR.

## API draft
| Method | Endpoint | Peran |
|---|---|---|
| GET | `/api/containers/{qr_id}` | Role sesuai akses |
| POST | `/api/containers/{id}/cycles` | SETTING_STAFF |
| PUT | `/api/cycles/{id}/composition-draft` | SETTING_STAFF |
| POST | `/api/cycles/{id}/verify` | SETTING_STAFF + validasi |
| POST | `/api/cycles/{id}/pack` | Role sesuai SOP |
| POST | `/api/batches` | STERILIZATION_STAFF |
| POST | `/api/cycles/{id}/qc-decision` | QC_OFFICER |
| POST | `/api/loans` | BORROWER |
| POST | `/api/loans/{id}/handover` | WAREHOUSE_STAFF |
| POST | `/api/returns` | Role penerimaan |
| POST | `/api/returns/{id}/verify` | DECONTAMINATION_STAFF |
| GET | `/api/discrepancies` | CSSD roles |
| POST | `/api/discrepancies/{id}/events` | Assigned role |
| GET | `/api/dashboard` | Sesuai akses |

Endpoint hanyalah contoh; implementasi perlu schema validation, auth, idempotency, codes, logging, pagination, error shape, dan transaction semantics.

## Pola transaksi
Saat handover: lock kontainer/siklus -> verifikasi state QC/expiry/availability -> tulis loan & items -> update location/status -> audit/outbox -> commit. Jika satu gagal, rollback. Sertakan idempotency key untuk double-tap.

## UI workflow
- Setting: satu halaman `Scan -> Template -> Counter input -> Physical Check -> Verify`.
- Gudang: daftar ready dan queue; batch scan, satu konfirmasi serah-terima.
- Peminjam: identitas dari login; jumlah langkah minimum.
- Dekontaminasi: scan loan, daftar alat terisi, angka aktual & pengecualian.
- Supervisor: dashboard, case list, filter dan riwayat.

## Mode demo
Seed contoh kontainer dan instrumen fiktif; QR demo mengarah ke data fiktif; belum menghubungkan SIMRS atau layanan pasien sungguhan.

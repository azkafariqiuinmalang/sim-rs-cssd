# DATA_MODEL — Draft Skema Relasional

**Database usulan:** PostgreSQL. Kolom di bawah konseptual; sesuaikan naming convention stack yang sudah ada.

| Entitas | Field utama | Keterangan |
|---|---|---|
| `users` | id, username, name, unit_id, role, can_release_qc | Akun pribadi dengan salah satu dari empat role. Izin QC hanya berlaku bagi petugas CSSD. |
| `units` | id, name, type | Gudang, OK, dekontaminasi, dll |
| `instrument_catalog` | id, code, name, active | Master jenis instrumen |
| `set_templates` | id, code, name, active | Jenis set standar |
| `set_template_versions` | id, template_id, version, approved_by | Versi komposisi |
| `set_template_items` | version_id, instrument_id, expected_qty | Jumlah nominal per jenis |
| `containers` | id, qr_public_id unique, label, type, active | QR permanen kontainer |
| `container_cycles` | id, container_id, template_version_id, sequence, state, created_by, timestamps | Siklus kontainer |
| `cycle_instruments` | cycle_id, instrument_id, verified_qty, condition_note | Snapshot hasil hitung fisik |
| `cycle_verifications` | id, cycle_id, actor_id, verified_at, note | Tanda tangan/verifikasi |
| `sterilization_batches` | id, machine_id, protocol_ref, started_at, completed_at, created_by | Detail wajib mengikuti SOP |
| `batch_cycles` | batch_id, cycle_id | Batch memuat beberapa siklus |
| `qc_decisions` | id, cycle_id, outcome, officer_id, at, evidence_ref, note | Keputusan berwenang |
| `loans` | id, unit_id, requested_by, status, handed_over_by, received_by, timestamps | Header transaksi multi-scan |
| `loan_items` | id, loan_id, container_id, cycle_id, handed_over_at, returned_at | Kontainer fisik per pinjam |
| `returns` | id, loan_id, unit_id, received_by, timestamp, status | Header penerimaan alat kotor |
| `return_items` | id, return_id, loan_item_id, instrument_id, expected_qty_snapshot, received_qty, condition | Real vs expected |
| `discrepancy_cases` | id, return_id, status, assigned_to, opened_at, resolved_at, resolution | Kasus ketidaksesuaian |
| `discrepancy_items` | case_id, instrument_id, expected_qty, actual_qty | Rincian selisih |
| `audit_events` | id, actor_id, actor_username, action, entity_type, entity_id, before_hash, after_hash, reason, timestamp | Append-only |
| `notifications` | id, target_role_or_user, case_id, status, created_at | Pengingat tanpa PII |

## Constraints yang wajib
- `containers.qr_public_id` unik, acak/tidak sequential bila ditampilkan publik.
- Unique `(container_id, sequence)` pada `container_cycles`.
- **Partial unique constraint**: satu siklus aktif terbuka per kontainer (definisi aktif dibuat eksplisit).
- `verified_qty`, `expected_qty`, `received_qty` integer >= 0.
- Unique `(cycle_id, instrument_id)` untuk snapshot satu jenis alat.
- `loan_items`: tidak boleh dua pinjaman belum-returned untuk `container_id` sama; gunakan transaction lock + unique/constraint yang mendukung state.
- Foreign key memaksa return terkait loan_item yang benar.
- Seluruh operasi handover/release/return memakai transaksi DB dan idempotency key.
- Template version yang sudah dipakai tidak diubah retroaktif; lakukan versioning.
- Snapshot data tetap walau instrumen/master kemudian dinonaktifkan.

## Catatan privasi
Jangan memasukkan patient name / nomor MR dalam inti alur demo. Jika benar-benar perlu integrasi pasien kelak, desain terpisah, minimisasi, otorisasi, retensi & review keamanan oleh RS.

## Computer Vision masa depan
Opsional tabel `instrument_detection_runs` (cycle_id, image_ref, model_version, predictions, confidence, reviewed_by) dengan `input_method` = `MANUAL|AI_ASSISTED`. Prediksi tidak menimpa `cycle_instruments` terverifikasi.

# IMPLEMENTATION_PLAN — Backlog Bertahap

## Phase 0 — Discovery & repo audit
- Inspeksi stack, auth, DB, infrastruktur, desain existing.
- Validasi master set, ownership QR, alur fisik dan status ke pemilik proses RS.
- Seed data sintetis. Deliverable: ERD teruji, screens/wireframe, decisions list.

## Phase 1 — Fondasi (P0)
- Auth, users, units, RBAC, audit.
- Master instrumen, master set + template version, kontainer + QR.
- Cycle creation + manual composition + physical verification + history.
- Tests: tidak menimpa siklus lama; role dan state constraints.

## Phase 2 — Siklus CSSD (P0)
- Packing, batch sterilization records, QC review/release/reject/quarantine.
- Dashboard gudang hanya set yang eligible.
- Tests: tidak bisa borrow set yang belum QC release.

## Phase 3 — Peminjaman cepat (P0)
- Bulk scan basket, login auto-fill identity, request/picking.
- Gudang konfirmasi handover atomik; audit; idempotency.
- Tests: double-loan concurrency, double-tap, incomplete batch.

## Phase 4 — Return & discrepancy (P0)
- Scan QR, resolve loan aktif, tampilkan snapshot alat.
- Entry jumlah aktual, mismatch handling, case, audit, notifikasi internal.
- Tests: expected 2 vs actual 1, exception, no automatic blame.

## Phase 5 — Dashboard & pilot (P1)
- Laporan harian, frekuensi pinjam per unit, outstanding loans, unresolved cases, QC rejected.
- Pilot di setting + gudang + ruang operasi + dekontaminasi; ukur waktu/langkah, perbaiki UX.
- Uji backup/restore, keamanan & akses.

## Phase 6 — Future options (P2)
- Integrasi SIMRS setelah API/izin tersedia.
- Computer Vision `AI_ASSISTED` + human validation, hanya setelah data anotasi dan validasi cukup.
- Batch request berbasis jadwal operasi jika data jadwal terstruktur tersedia.

## Prioritas untuk agent
Implementasi sebagai vertical slice **satu kontainer/satu siklus/satu transaksi** dahulu, lalu dukung multi-scan dan pengecualian. Jangan mengerjakan AI/LLM sebelum P0 teruji.

## Definition of Pilot Success
Dibanding Google Form baseline, ukur median waktu peminjaman, frekuensi input nama alat, tingkat kelengkapan audit, jumlah transaksi double-loan (target nol), serta waktu pelaporan discrepancy. Target numerik ditetapkan bersama RS.

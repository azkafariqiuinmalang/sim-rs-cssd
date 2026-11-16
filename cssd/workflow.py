import re

from flask import abort

from .db import instrument_display_name


def row(conn, sql, args=()):
    found = conn.execute(sql, args).fetchone()
    if found is None:
        abort(404, "Data tidak ditemukan.")
    return found


def text(form, field, label, limit=200):
    value = form.get(field, "").strip()
    if not value or len(value) > limit:
        abort(400, f"{label} wajib diisi dan maksimal {limit} karakter.")
    return value


def quantities(form, items, returning=False):
    if form.get("physical_check") != "yes":
        abort(400, "Konfirmasi pemeriksaan fisik wajib diisi.")
    result = []
    for item in items:
        instrument = item["instrument_id"]
        key = f"qty_{instrument}"
        values = form.getlist(key)
        if returning:
            confirmation = form.getlist(f"count_{instrument}")
            if confirmation == ["match"]:
                values = [str(item["verified"])]
            elif confirmation not in ([], ["different"]):
                abort(400, "Pilih hasil pemeriksaan per instrumen.")
        if len(values) != 1 or not re.fullmatch(r"[0-9]{1,5}", values[0]):
            abort(400, f"Isi jumlah fisik yang valid untuk {item['name']}.")
        note = form.get(f"note_{instrument}", "").strip()
        if len(note) > 200:
            abort(400, "Catatan kondisi maksimal 200 karakter.")
        result.append((item, int(values[0]), note))
    return result


def require_state(record, expected):
    if record["state"] not in expected:
        abort(409, "Status berubah atau tindakan belum tersedia. Muat ulang halaman.")


def active_cycle(conn, container_id):
    return conn.execute(
        "SELECT * FROM cycles WHERE container_id=? AND closed_at IS NULL", (container_id,)
    ).fetchone()


def template_items(conn, template_id):
    return conn.execute(
        """SELECT ti.instrument_id, i.name, ti.expected FROM template_items ti
        JOIN instruments i ON i.id=ti.instrument_id WHERE ti.template_id=? ORDER BY i.name""",
        (template_id,),
    ).fetchall()


def snapshot(conn, cycle_id):
    return snapshots(conn, [cycle_id]).get(cycle_id, [])


def snapshots(conn, cycle_ids):
    if not cycle_ids:
        return {}
    placeholders = ",".join("?" for _ in cycle_ids)
    items = conn.execute(
        f"SELECT * FROM cycle_items WHERE cycle_id IN ({placeholders}) ORDER BY instrument_id", tuple(cycle_ids),
    )
    result = {}
    for item in items:
        result.setdefault(item["cycle_id"], []).append(dict(item, name=instrument_display_name(item["name"])))
    return result


def availability(conn, cycle_id):
    return row(conn, """
        SELECT c.state, c.closed_at, qc.outcome, EXISTS (
            SELECT 1 FROM cycle_items ci WHERE ci.cycle_id=c.id AND ci.expected<>ci.verified
        ) AS variation
        FROM cycles c LEFT JOIN qc_decisions qc ON qc.cycle_id=c.id WHERE c.id=?
    """, (cycle_id,))


def eligible(conn, cycle_id):
    info = availability(conn, cycle_id)
    return (
        info["state"] == "AVAILABLE" and info["closed_at"] is None
        and info["outcome"] == "RELEASE" and not info["variation"]
    )


def active_loan_item(conn, container_id):
    return conn.execute("""
        SELECT li.*, l.state AS loan_state, l.unit_id FROM loan_items li
        JOIN loans l ON l.id=li.loan_id
        WHERE li.container_id=? AND li.handed_at IS NOT NULL AND li.returned_at IS NULL
    """, (container_id,)).fetchone()


def loan_items(conn, loan_id):
    return conn.execute("""
        SELECT li.*, c.label, c.qr, t.name AS set_name, r.id AS return_id
        FROM loan_items li JOIN containers c ON c.id=li.container_id
        JOIN cycles cy ON cy.id=li.cycle_id JOIN templates t ON t.id=cy.template_id
        LEFT JOIN returns r ON r.loan_item_id=li.id
        WHERE li.loan_id=? ORDER BY li.id
    """, (loan_id,)).fetchall()


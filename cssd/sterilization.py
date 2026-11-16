from flask import abort

from .db import insert


def history(conn, cycle_ids):
    if not cycle_ids:
        return {}
    placeholders = ",".join("?" for _ in cycle_ids)
    rows = conn.execute(f"""
        SELECT bc.cycle_id,b.reference,b.process_evidence,b.completed_at,u.name AS operator
        FROM batch_cycles bc JOIN batches b ON b.id=bc.batch_id JOIN users u ON u.id=b.operator_id
        WHERE bc.cycle_id IN ({placeholders})
    """, tuple(cycle_ids))
    return {row["cycle_id"]: row for row in rows}


def for_cycle(conn, cycle_id):
    return conn.execute("""
        SELECT b.*, u.name AS operator FROM batches b
        JOIN batch_cycles bc ON bc.batch_id=b.id JOIN users u ON u.id=b.operator_id
        WHERE bc.cycle_id=?
    """, (cycle_id,)).fetchone()


def members(conn, batch_id):
    return conn.execute("""
        SELECT cy.id, cy.state, cy.closed_at, c.label, c.qr
        FROM batch_cycles bc JOIN cycles cy ON cy.id=bc.cycle_id
        JOIN containers c ON c.id=cy.container_id
        WHERE bc.batch_id=? ORDER BY c.label
    """, (batch_id,)).fetchall()


def start(conn, actor, cycle_ids, reference):
    placeholders = ",".join("?" for _ in cycle_ids)
    cycles = conn.execute(f"""
        SELECT id FROM cycles WHERE id IN ({placeholders}) AND state='PACKAGED' AND closed_at IS NULL
    """, tuple(cycle_ids)).fetchall()
    if len(cycles) != len(cycle_ids):
        abort(409, "Semua kontainer harus sudah dikemas dan memiliki siklus aktif.")
    batch_id = insert(conn, "INSERT INTO batches(reference,operator_id) VALUES(?,?)", (reference, actor))
    conn.executemany("INSERT INTO batch_cycles(cycle_id,batch_id) VALUES(?,?)", [
        (cycle_id, batch_id) for cycle_id in cycle_ids
    ])
    conn.execute(f"UPDATE cycles SET state='PROCESSING' WHERE id IN ({placeholders})", tuple(cycle_ids))
    return batch_id


def complete(conn, cycle_id, evidence):
    batch = for_cycle(conn, cycle_id)
    if not batch or batch["completed_at"]:
        abort(409, "Batch aktif tidak ditemukan.")
    included = members(conn, batch["id"])
    if not included or any(item["state"] != "PROCESSING" or item["closed_at"] for item in included):
        abort(409, "Status kontainer dalam batch berubah. Muat ulang halaman.")
    conn.execute("UPDATE batches SET completed_at=CURRENT_TIMESTAMP,process_evidence=? WHERE id=?",
                 (evidence, batch["id"]))
    conn.execute("""
        UPDATE cycles SET state='QC_PENDING'
        WHERE id IN (SELECT cycle_id FROM batch_cycles WHERE batch_id=?)
    """, (batch["id"],))
    return batch["id"], [item["id"] for item in included]

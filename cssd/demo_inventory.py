"""Synthetic catalog and transaction fixtures for the RSUD Grati demo."""

import json
import secrets

from . import sterilization
from .db import insert


BEDAH_MINOR = {
    "Gagang bisturi No. 3": 1, "Pinset Anatomi": 1, "Pinset Chirurgis": 1,
    "Klem Hemostat Mosquito Lurus": 2, "Klem Hemostat Mosquito Bengkok": 2,
    "Gunting Metzenbaum Lengkung": 1, "Gunting Mayo Lurus": 1, "Pemegang jarum Mayo-Hegar": 1,
}
BEDAH_UMUM = {
    **BEDAH_MINOR, "Gagang bisturi No. 4": 1, "Klem Kelly Lengkung": 4,
    "Klem Kocher Lurus": 2, "Klem Allis": 4, "Klem Babcock": 2,
    "Klem handuk Backhaus": 4, "Retraktor Farabeuf": 2, "Gunting Mayo Lengkung": 1,
}
SET_TEMPLATES = {
    "Set Bedah Minor": BEDAH_MINOR,
    "Set Bedah Umum": BEDAH_UMUM,
    "Set Laparotomi": {
        **BEDAH_UMUM, "Klem Pean Panjang": 4, "Retraktor Deaver": 2,
        "Retraktor Richardson": 2, "Kanula suction Yankauer logam": 1,
    },
    "Set Seksio Sesarea": {
        **BEDAH_UMUM, "Klem Green-Armytage": 4, "Retraktor Doyen": 1,
        "Klem kasa Foerster": 2, "Klem Pean Panjang": 2,
    },
    "Set Ortopedi Dasar": {
        "Retraktor Hohmann": 2, "Elevator periosteum": 2, "Osteotom": 2,
        "Palu tulang": 1, "Rongeur tulang": 1, "Kuret tulang": 2,
        "Klem tulang Verbrugge": 2, "Pemegang jarum Mayo-Hegar": 1, "Klem Kelly Lengkung": 2,
    },
    "Set Bedah THT Dasar": {
        "Spekulum hidung Killian": 1, "Pinset bayonet": 1, "Klem Hartmann THT": 1,
        "Kanula suction Frazier logam": 1, "Elevator Freer": 1, "Gunting Metzenbaum Lengkung": 1,
    },
    "Set Ekstraksi Gigi": {
        "Tang ekstraksi gigi rahang atas": 1, "Tang ekstraksi gigi rahang bawah": 1,
        "Elevator akar gigi Bein": 1, "Elevator Cryer Kiri": 1,
        "Elevator Cryer Kanan": 1, "Kuret alveolar": 1,
    },
    "Set Jahit Luka": {
        "Pemegang jarum Mayo-Hegar": 1, "Pinset Chirurgis": 1,
        "Klem Hemostat Mosquito Lurus": 2, "Gunting Mayo Lurus": 1,
    },
    "Set Rawat Luka": {
        "Pinset Anatomi": 2, "Pinset Chirurgis": 1, "Gunting perban Lister": 1,
        "Klem kasa Foerster": 1, "Baki ginjal stainless": 1,
    },
    "Set Lepas Jahitan": {
        "Gunting jahitan Spencer": 1, "Pinset Anatomi": 1, "Baki ginjal stainless": 1,
    },
    "Set Persalinan Normal": {
        "Gunting tali pusat": 1, "Klem Kelly Lengkung": 2, "Klem kasa Foerster": 1,
        "Pinset Anatomi": 1, "Pemegang jarum Mayo-Hegar": 1, "Baki ginjal stainless": 1,
    },
    "Set Pemeriksaan Ginekologi": {
        "Spekulum vagina Cusco": 1, "Klem kasa Foerster": 1,
        "Pinset Anatomi": 1, "Baki ginjal stainless": 1,
    },
    "Set Pemeriksaan Gigi": {
        "Kaca mulut gigi": 1, "Sonde gigi": 1, "Pinset gigi College": 1,
    },
    "Set Pemeriksaan THT": {
        "Spekulum hidung Killian": 1, "Pinset bayonet": 1,
        "Spekulum telinga logam": 2, "Klem Hartmann THT": 1,
    },
    "Set Pengangkatan Benda Asing Superfisial": {
        "Pinset Adson bergigi": 1, "Pinset Anatomi": 1,
        "Klem Hemostat Mosquito Bengkok": 1, "Baki ginjal stainless": 1,
    },
    "Set Perawatan Tali Pusat": {
        "Pinset Anatomi": 1, "Klem kasa Foerster": 1, "Baki ginjal stainless": 1,
    },
}
SINGLE_PACKS = {
    "Pinset Anatomi": 2, "Pinset Chirurgis": 1, "Klem Hemostat Mosquito Lurus": 2,
    "Klem Kelly Lengkung": 1, "Gunting Metzenbaum Lengkung": 1, "Gunting Mayo Lurus": 1,
    "Pemegang jarum Mayo-Hegar": 1, "Gunting perban Lister": 1,
    "Klem kasa Foerster": 1, "Spekulum vagina Cusco": 1,
}
SPARE_STATES = ("AVAILABLE", "PACKAGED", "PROCESSING", "QC_PENDING", "BORROWED", "DRAFT")


def seed_inventory(conn):
    """Populate an empty catalog inside the caller's transaction."""
    if conn.execute("SELECT 1 FROM containers LIMIT 1").fetchone():
        raise ValueError("Inventaris demo harus kosong sebelum pengisian.")
    users = {account["username"]: account for account in conn.execute(
        "SELECT id,username,unit_id,role,can_release_qc FROM users"
    )}
    expected_roles = {
        "setting": "petugas_cssd", "steril": "petugas_cssd", "qc": "petugas_cssd",
        "gudang": "petugas_cssd", "ok": "petugas_unit", "ok2": "petugas_unit",
    }
    if any(name not in users or users[name]["role"] != role for name, role in expected_roles.items()) or not users["qc"]["can_release_qc"]:
        raise ValueError("Akun demo untuk alur CSSD belum lengkap.")

    catalog = {**SET_TEMPLATES, **{name: {name: 1} for name in SINGLE_PACKS}}
    instrument_ids = {
        name: insert(conn, "INSERT INTO instruments(name) VALUES(?)", (name,))
        for name in sorted({name for composition in catalog.values() for name in composition})
    }
    templates = {}
    for name, composition in catalog.items():
        template = insert(conn, "INSERT INTO templates(name,version) VALUES(?,1)", (name,))
        templates[name] = template
        conn.executemany("INSERT INTO template_items VALUES(?,?,?)", [
            (template, instrument_ids[instrument], quantity) for instrument, quantity in composition.items()
        ])

    inventory = []
    for index, name in enumerate(SET_TEMPLATES):
        inventory.extend(((name, "AVAILABLE"), (name, SPARE_STATES[index % len(SPARE_STATES)])))
    for name, count in SINGLE_PACKS.items():
        inventory.extend([(name, "AVAILABLE")] * count)
    inventory.extend((name, None) for name in ("Set Bedah Minor", "Set Rawat Luka", "Set Jahit Luka"))
    ready_batches = []
    active_batch = []
    checked = []
    borrowed = []
    for index, (name, state) in enumerate(inventory, start=1):
        template = templates[name]
        item = insert(conn, "INSERT INTO containers(label,qr,template_id) VALUES(?,?,?)",
                      (f"C-{index:03}", secrets.token_urlsafe(18), template))
        if state is None:
            continue
        cycle = insert(conn, """
            INSERT INTO cycles(container_id,template_id,sequence,state,created_by)
            VALUES(?,?,1,'DRAFT',?)
        """, (item, template, users["setting"]["id"]))
        if state == "DRAFT":
            continue
        conn.executemany("INSERT INTO cycle_items VALUES(?,?,?,?,?,?)", [
            (cycle, instrument_ids[instrument], instrument, quantity, quantity, "")
            for instrument, quantity in catalog[name].items()
        ])
        conn.execute("""
            UPDATE cycles SET state='PACKAGED',verified_by=?,verified_at=CURRENT_TIMESTAMP WHERE id=?
        """, (users["setting"]["id"], cycle))
        if state == "PACKAGED":
            continue
        if state == "PROCESSING":
            active_batch.append(cycle)
            continue
        ready_batches.append(cycle)
        if state in {"AVAILABLE", "BORROWED"}:
            checked.append(cycle)
        if state == "BORROWED":
            borrowed.append((item, cycle))

    if active_batch:
        sterilization.start(conn, users["steril"]["id"], active_batch, "SIM-GRATI-PROSES")
    for offset in range(0, len(ready_batches), 6):
        members = ready_batches[offset:offset + 6]
        reference = f"SIM-GRATI-{offset // 6 + 1:02}"
        sterilization.start(conn, users["steril"]["id"], members, reference)
        sterilization.complete(conn, members[0], f"BUKTI-SIM-{reference}")
    conn.executemany("INSERT INTO qc_decisions(cycle_id,outcome,evidence,officer_id) VALUES(?,'RELEASE',?,?)", [
        (cycle, f"QC-SIM-{cycle:03}", users["qc"]["id"]) for cycle in checked
    ])
    conn.executemany("UPDATE cycles SET state='AVAILABLE' WHERE id=?", [(cycle,) for cycle in checked])
    for index, (item, cycle) in enumerate(borrowed):
        recipient = users["ok" if index % 2 == 0 else "ok2"]
        loan = insert(conn, """
            INSERT INTO loans(unit_id,requester,state,handed_over_by,handed_over_at,received_by,received_at)
            VALUES(?,?,'RECEIVED',?,CURRENT_TIMESTAMP,?,CURRENT_TIMESTAMP)
        """, (recipient["unit_id"], recipient["id"], users["gudang"]["id"], recipient["id"]))
        conn.execute("INSERT INTO loan_items(loan_id,container_id,cycle_id,handed_at) VALUES(?,?,?,CURRENT_TIMESTAMP)",
                     (loan, item, cycle))
        conn.execute("UPDATE cycles SET state='BORROWED' WHERE id=?", (cycle,))
    conn.execute("""
        INSERT INTO audit_events(actor_id,actor_username,action,entity,entity_id,reason,details)
        VALUES(?,'setting','SEED_DEMO_INVENTORY','inventory',0,?,?)
    """, (users["setting"]["id"], "Pemuatan inventaris simulasi RSUD Grati",
          json.dumps({"containers": len(inventory), "sets": len(SET_TEMPLATES), "instruments": len(instrument_ids)})))

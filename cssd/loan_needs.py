import re
from collections import Counter

from flask import abort

from .db import instrument_display_name
from .workflow import snapshots


def catalog(conn, custom):
    instruments = conn.execute("SELECT id, name FROM instruments ORDER BY name").fetchall()
    kinds = {"custom" if custom else "piece": [
        {"id": item["id"], "name": instrument_display_name(item["name"])} for item in instruments
    ]}
    if not custom:
        sets = conn.execute("""
            SELECT MIN(t.id) AS id, t.name FROM templates t
            WHERE t.name NOT LIKE 'Set khusus C-%'
              AND t.id IN (SELECT template_id FROM template_items GROUP BY template_id HAVING SUM(expected)>1)
            GROUP BY t.name ORDER BY t.name
        """).fetchall()
        kinds = {"set": sets, **kinds}
    return kinds


def requested_lines(form, options):
    lines = []
    for kind, choices in options.items():
        for item in choices:
            values = form.getlist(f"{kind}_{item['id']}")
            if not values or values == [""]:
                continue
            if len(values) != 1 or not re.fullmatch(r"[0-9]{1,5}", values[0]) or int(values[0]) < 1:
                abort(400, f"Isi jumlah yang valid untuk {item['name']}.")
            lines.append((kind, item["name"], None if kind == "set" else item["id"], int(values[0])))
    if not lines:
        abort(400, "Isi jumlah untuk set atau alat yang dibutuhkan.")
    if "custom" not in options and sum(line[3] for line in lines) > 20:
        abort(400, "Ajukan maksimal 20 kontainer atau kemasan dalam satu transaksi.")
    return lines


def for_loan(conn, loan_id):
    return conn.execute("""
        SELECT kind, item_name, instrument_id, quantity
        FROM loan_needs WHERE loan_id=? ORDER BY CASE kind WHEN 'set' THEN 0 ELSE 1 END, item_name
    """, (loan_id,)).fetchall()


def matching_stock(conn, needs, stock):
    if needs[0]["kind"] == "custom":
        expected = {line["instrument_id"]: line["quantity"] for line in needs}
        compositions = snapshots(conn, [item["cycle_id"] for item in stock])
        return [item for item in stock if {
            part["instrument_id"]: part["verified"]
            for part in compositions.get(item["cycle_id"], []) if part["verified"] > 0
        } == expected]
    keys = {need_key(line) for line in needs}
    return [item for item in stock if stock_key(item) in keys]


def need_key(line):
    return (line["kind"], line["instrument_id"] if line["kind"] == "piece" else line["item_name"])


def stock_key(item):
    if item["instrument_id"] is not None:
        return ("piece", item["instrument_id"])
    return ("set", item["set_name"])


def complete(needs, packages):
    if needs[0]["kind"] == "custom":
        return len(packages) == 1
    expected = Counter({need_key(line): line["quantity"] for line in needs})
    return Counter(stock_key(item) for item in packages) == expected

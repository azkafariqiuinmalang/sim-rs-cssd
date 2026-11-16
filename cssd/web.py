import hashlib
import hmac
import json
import re
import secrets
from datetime import date, datetime, time, timedelta, timezone
from functools import wraps
from io import BytesIO
from time import time as unix_time
from zoneinfo import ZoneInfo

from flask import (
    Blueprint, abort, current_app, g, redirect, render_template, request,
    send_file, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, loan_needs, sterilization, supabase_auth
from .db import insert
from .report_export import write_workbook
from .workflow import (
    active_cycle, active_loan_item, availability, eligible, loan_items,
    quantities, require_state, row, snapshot, snapshots, template_items, text,
)

bp = Blueprint("web", __name__)
ROLE_LABELS = {
    "admin": "Admin Sistem",
    "petugas_cssd": "Petugas CSSD",
    "petugas_unit": "Petugas Unit",
    "supervisor": "Supervisor CSSD",
}
DEMO_ACCOUNTS = (
    ("admin", "Admin Sistem", "Daftarkan instrumen, kelola akun, dan pantau audit."),
    ("setting", "Petugas CSSD", "Verifikasi isi kontainer dan proses permintaan unit."),
    ("ok", "Petugas Unit · OK Demo A", "Ajukan pinjaman dan konfirmasi penerimaan."),
    ("supervisor", "Supervisor CSSD", "Selidiki selisih dan lihat laporan harian."),
    ("qc", "Petugas CSSD · Izin QC", "Bandingkan akses keputusan QC dengan akun setting."),
    ("ok2", "Petugas Unit · OK Demo B", "Bandingkan transaksi dari dua unit berbeda."),
)
TRUSTED = ("admin", "petugas_cssd", "supervisor")
CSSD_MODULES = {
    "setting": ("Setting Alat", "Komposisi dan pengemasan",
                (None, "DIRTY_RECEIVED", "DISCREPANCY", "DECONTAMINATED", "DRAFT", "VERIFIED")),
    "sterilisasi": ("Sterilisasi", "Batch dan proses", ("PACKAGED", "PROCESSING")),
    "qc": ("Quality Control", "Antrean pemeriksaan dan keputusan", ("QC_PENDING", "AVAILABLE", "REJECTED", "QUARANTINED")),
    "gudang": ("Gudang", "Stok dan peminjaman", ("AVAILABLE",)),
    "dekontaminasi": ("Dekontaminasi", "Pengembalian dan pemrosesan ulang", ("BORROWED", "DIRTY_RECEIVED")),
    "riwayat": ("Riwayat", "Siklus kontainer", ()),
}
LOAN_STATUS_LABELS = {
    "REQUESTED": "Menunggu proses", "PICKING": "Sedang disiapkan", "HANDED_OVER": "Diserahkan",
    "RECEIVED": "Diterima unit", "PARTIALLY_RETURNED": "Sebagian kembali",
    "RETURNED": "Sudah kembali", "CANCELLED": "Dibatalkan",
}
ACCOUNT_ENUMERATION_HASH = generate_password_hash(secrets.token_hex(24))


@bp.app_template_filter("localtime")
def localtime(value):
    if not value:
        return "—"
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    utc = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return utc.astimezone(ZoneInfo("Asia/Jakarta")).strftime("%d/%m/%Y %H:%M WIB")


@bp.before_request
def identify():
    g.actor = None
    using_supabase = bool(current_app.config["SUPABASE_URL"])
    if "actor" in session:
        if using_supabase and session.get("supabase_id") and session.get("supabase_expires_at", 0) > unix_time():
            g.actor = db.get().execute(
                "SELECT * FROM users WHERE id=? AND auth_user_id=?",
                (session["actor"], session["supabase_id"]),
            ).fetchone()
        elif not using_supabase and not session.get("supabase_id"):
            g.actor = db.get().execute("SELECT * FROM users WHERE id=?", (session["actor"],)).fetchone()
        if g.actor is None:
            session.clear()
    if request.method == "POST":
        token = session.get("csrf", "")
        if not token or not secrets.compare_digest(token.encode(), request.form.get("csrf", "").encode()):
            abort(400, "Sesi formulir tidak valid. Muat ulang halaman.")


@bp.after_request
def prevent_session_page_cache(response):
    if g.get("actor") is not None or request.endpoint == "web.login":
        response.cache_control.no_store = True
    return response


@bp.context_processor
def form_tokens():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return {"csrf": session["csrf"], "key": lambda: secrets.token_urlsafe(24), "role_labels": ROLE_LABELS,
            "loan_status_labels": LOAN_STATUS_LABELS}


def authorized(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.actor is None:
                if request.method == "GET":
                    return redirect(url_for("web.login", next=request.path))
                abort(401, "Silakan masuk kembali.")
            if roles and g.actor["role"] not in roles:
                abort(403, "Akses ditolak untuk peran ini.")
            return view(*args, **kwargs)
        return wrapped
    return decorate


def numeric_id(value):
    if not value or not re.fullmatch(r"[0-9]{1,10}", value) or not 0 < int(value) <= 2_147_483_647:
        abort(400, "ID tidak valid.")
    return int(value)


def mutation(action, entity, handler):
    conn = db.get()
    idem = text(request.form, "key", "ID konfirmasi", 100)
    payload = [request.path, sorted((k, v) for k, v in request.form.lists() if k not in {"csrf", "key"})]
    encoded = json.dumps(payload, ensure_ascii=False).encode()
    if action == "CREATE_USER":
        secret = current_app.secret_key
        digest = hmac.digest(secret.encode() if isinstance(secret, str) else secret, encoded, "sha256").hex()
    else:
        # Preserve the fingerprint format for confirmation keys already recorded.
        digest = hashlib.sha256(encoded).hexdigest()
    actor = g.actor["id"]
    try:
        with db.write_transaction(conn):
            current_actor = row(conn, "SELECT role, unit_id, can_release_qc, username FROM users WHERE id=?", (actor,))
            if any(current_actor[field] != g.actor[field] for field in current_actor.keys()):
                abort(403, "Hak akses berubah. Muat ulang halaman.")
            prior = conn.execute(
                "SELECT * FROM idempotency WHERE actor_id=? AND idem_key=?", (actor, idem)
            ).fetchone()
            if prior:
                if prior["request_hash"] != digest:
                    abort(409, "ID konfirmasi sudah dipakai untuk permintaan berbeda.")
                result = prior["redirect_to"]
            else:
                entity_id, result, reason, details = handler(conn, actor)
                conn.execute("""INSERT INTO audit_events(actor_id,actor_username,action,entity,entity_id,reason,details)
                             VALUES(?,?,?,?,?,?,?)""",
                             (actor, current_actor["username"], action, entity, entity_id, reason,
                              json.dumps(details, ensure_ascii=False)))
                conn.execute("INSERT INTO idempotency VALUES(?,?,?,?)", (actor, idem, digest, result))
    except Exception as exc:
        if db.is_conflict(exc):
            abort(409, "Data ganda atau konflik status. Muat ulang halaman.")
        if db.is_retryable(exc):
            abort(503, "Database sibuk. Ulangi konfirmasi yang sama.")
        raise
    return redirect(result, code=303)


@bp.app_errorhandler(400)
@bp.app_errorhandler(401)
@bp.app_errorhandler(403)
@bp.app_errorhandler(404)
@bp.app_errorhandler(409)
@bp.app_errorhandler(413)
@bp.app_errorhandler(503)
def error_page(error):
    return render_template("error.html", error=error), error.code


@bp.route("/login", methods=["GET", "POST"])
def login():
    next_path = request.values.get("next", "")
    if not next_path.startswith("/c/") or not next_path.removeprefix("/c/").replace("-", "").replace("_", "").isalnum():
        next_path = ""
    if request.method == "GET" and g.actor:
        return redirect(next_path or url_for("web.dashboard"))

    auth_url = current_app.config["SUPABASE_URL"]
    demo_accounts = DEMO_ACCOUNTS if current_app.config["DEMO_GUIDE"] else ()
    if auth_url:
        demo_accounts = tuple((f"{account}@steritrack.example.com", label, task)
                              for account, label, task in demo_accounts)
    username = request.args.get("akun", "")
    if not any(username == account[0] for account in demo_accounts):
        username = ""
    if request.method == "POST":
        username = text(request.form, "username", "Akun", 254 if auth_url else 50)
        password = request.form.get("password", "")
        if not password or len(password) > 200:
            abort(400, "Sandi tidak valid.")
        auth_identity = None
        if auth_url:
            try:
                auth_identity = supabase_auth.sign_in(
                    auth_url, current_app.config["SUPABASE_PUBLISHABLE_KEY"], username.lower(), password,
                )
            except supabase_auth.AuthUnavailable:
                abort(503, "Supabase Auth sedang tidak tersedia. Coba lagi.")
            user = db.get().execute(
                "SELECT id FROM users WHERE auth_user_id=?", (auth_identity[0],)
            ).fetchone() if auth_identity else None
        else:
            user = db.get().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not check_password_hash(user["password_hash"] if user else ACCOUNT_ENUMERATION_HASH, password.strip()):
                user = None
        if user is None:
            return render_template(
                "login.html", error="Akun atau sandi salah.",
                next_path=next_path, username=username, demo_accounts=demo_accounts, email_login=bool(auth_url),
            ), 401
        session.clear()
        session["actor"] = user["id"]
        if auth_identity:
            session["supabase_id"], session["supabase_expires_at"] = auth_identity
        return redirect(next_path or url_for("web.dashboard"), code=303)
    return render_template(
        "login.html", next_path=next_path, username=username, demo_accounts=demo_accounts, email_login=bool(auth_url),
    )


@bp.post("/logout")
@authorized()
def logout():
    session.clear()
    return redirect(url_for("web.login"), code=303)


AVAILABLE_STOCK = """
    cy.state='AVAILABLE'
    AND EXISTS (SELECT 1 FROM qc_decisions q WHERE q.cycle_id=cy.id AND q.outcome='RELEASE')
    AND NOT EXISTS (SELECT 1 FROM cycle_items ci WHERE ci.cycle_id=cy.id AND ci.expected<>ci.verified)
"""
ACTIVE_CONTAINER_STOCK = """
    SELECT c.label, c.qr, cy.id AS cycle_id, cy.state, t.name AS set_name
    FROM containers c JOIN cycles cy ON cy.container_id=c.id AND cy.closed_at IS NULL
    JOIN templates t ON t.id=cy.template_id
"""
SINGLE_INSTRUMENT = """
    LEFT JOIN cycle_items ci
        ON ci.cycle_id=stock.cycle_id AND ci.verified=1
        AND NOT EXISTS (
            SELECT 1 FROM cycle_items other
            WHERE other.cycle_id=ci.cycle_id AND other.instrument_id<>ci.instrument_id
                AND other.verified>0
        )
"""


WAREHOUSE_QUEUE = "l.state IN ('REQUESTED','PICKING')"
CSSD_ACTION_QUEUES = (
    ("Verifikasi komposisi alat", "setting", "DRAFT"),
    ("Mulai sterilisasi", "sterilisasi", "PACKAGED"),
    ("Sterilisasi sedang berjalan", "sterilisasi", "PROCESSING"),
    ("Tinjau hasil QC", "qc", "QC_PENDING"),
    ("Catat dekontaminasi", "dekontaminasi", "DIRTY_RECEIVED"),
)


def dashboard_actions(conn, actor, containers):
    role = actor["role"]
    if role == "petugas_cssd":
        actions = [
            {
                "label": label,
                "total": sum(item["state"] == state for item in containers),
                "url": url_for("web.dashboard", modul=module, status=state, _anchor="daftar-kontainer"),
            }
            for label, module, state in CSSD_ACTION_QUEUES
            if module != "qc" or actor["can_release_qc"]
        ]
        total = conn.execute("SELECT COUNT(*) AS total FROM loans l WHERE " + WAREHOUSE_QUEUE).fetchone()["total"]
        actions.append({
            "label": "Siapkan atau serahkan pinjaman", "total": total,
            "url": url_for("web.dashboard", modul="gudang", _anchor="antrean-gudang"),
        })
        return actions
    if role == "petugas_unit":
        pending = conn.execute("""
            SELECT id FROM loans WHERE unit_id=? AND received_by=? AND state='HANDED_OVER' ORDER BY id
        """, (actor["unit_id"], actor["id"])).fetchall()
        return [
            {"label": f"Konfirmasi penerimaan pinjaman #{loan['id']}",
             "url": url_for("web.loan_detail", loan_id=loan["id"], _anchor="konfirmasi-penerimaan")}
            for loan in pending
        ]
    if role == "supervisor":
        return [{
            "label": "Tindak lanjuti kasus selisih",
            "total": len(report_open_cases(conn, None)),
            "url": url_for("web.reports", _anchor="kasus-aktif"),
        }]
    return None


@bp.get("/")
@authorized()
def dashboard():
    conn = db.get()
    role = g.actor["role"]
    module = request.args.get("modul", "")
    status = request.args.get("status", "")
    if module and (role != "petugas_cssd" or module not in CSSD_MODULES):
        abort(404)
    if status and (not module or status not in CSSD_MODULES[module][2]):
        abort(404)
    page = numeric_id(request.args.get("halaman", "1")) if module else 1
    page_size = 50
    if role == "petugas_unit":
        containers = conn.execute(ACTIVE_CONTAINER_STOCK + f"""
            WHERE ({AVAILABLE_STOCK}) OR EXISTS (
                SELECT 1 FROM loan_items li JOIN loans l ON l.id=li.loan_id
                WHERE li.cycle_id=cy.id AND l.unit_id=? AND li.handed_at IS NOT NULL AND li.returned_at IS NULL
            ) ORDER BY c.label
        """, (g.actor["unit_id"],)).fetchall()
    elif module == "gudang":
        containers = conn.execute(
            ACTIVE_CONTAINER_STOCK + " WHERE " + AVAILABLE_STOCK + " ORDER BY c.label LIMIT ? OFFSET ?",
            (page_size + 1, (page - 1) * page_size),
        ).fetchall()
    else:
        inventory_sql = """
            SELECT c.label, c.qr, cy.id AS cycle_id, COALESCE(cy.state, (
                SELECT history.state FROM cycles history
                WHERE history.container_id=c.id AND history.closed_at IS NOT NULL
                ORDER BY history.sequence DESC LIMIT 1
            )) AS state, t.name AS set_name
            FROM containers c LEFT JOIN cycles cy ON cy.container_id=c.id AND cy.closed_at IS NULL
            JOIN templates t ON t.id=COALESCE(cy.template_id,c.template_id)
        """
        params = []
        query = f"WITH inventory AS ({inventory_sql}) SELECT * FROM inventory"
        if module:
            states = (status,) if status else CSSD_MODULES[module][2]
            params.extend(state for state in states if state is not None)
            filters = []
            if params:
                filters.append("state IN (" + ",".join("?" for _ in params) + ")")
            if None in states:
                filters.append("state IS NULL")
            if filters:
                query += " WHERE " + " OR ".join(filters)
        query += " ORDER BY label"
        if module:
            query += " LIMIT ? OFFSET ?"
            params.extend((page_size + 1, (page - 1) * page_size))
        containers = conn.execute(query, tuple(params)).fetchall()
    has_next = bool(module and len(containers) > page_size)
    if module:
        containers = containers[:page_size]
    show_loans = not module or module == "gudang"
    loan_query = "SELECT l.*, u.name AS unit FROM loans l JOIN units u ON u.id=l.unit_id"
    loans = []
    if role == "petugas_unit":
        loans = conn.execute(loan_query + " WHERE l.unit_id=? ORDER BY l.id DESC LIMIT 30", (g.actor["unit_id"],)).fetchall()
    elif module == "gudang":
        loans = conn.execute(
            loan_query + " WHERE " + WAREHOUSE_QUEUE + " ORDER BY l.id"
        ).fetchall()
    elif show_loans:
        loans = conn.execute(loan_query + " ORDER BY l.id DESC LIMIT 30").fetchall()
    loan_contents = {}
    if role == "petugas_unit" and loans:
        placeholders = ",".join("?" for _ in loans)
        for item in conn.execute(f"""
            SELECT li.loan_id, c.label, t.name AS set_name
            FROM loan_items li JOIN containers c ON c.id=li.container_id
            JOIN cycles cy ON cy.id=li.cycle_id JOIN templates t ON t.id=cy.template_id
            WHERE li.loan_id IN ({placeholders}) ORDER BY c.label
        """, tuple(loan["id"] for loan in loans)):
            loan_contents.setdefault(item["loan_id"], []).append(item)
    cases = []
    if role == "supervisor":
        cases = conn.execute("""
            SELECT dc.*, n.id AS notification_id FROM discrepancy_cases dc
            JOIN notifications n ON n.case_id=dc.id ORDER BY dc.id DESC LIMIT 30
        """).fetchall()
    unit = row(conn, "SELECT name FROM units WHERE id=?", (g.actor["unit_id"],))["name"]
    return render_template(
        "dashboard.html", containers=containers, loans=loans, loan_contents=loan_contents, cases=cases, unit=unit,
        modules=CSSD_MODULES, module=module, status=status, show_loans=show_loans,
        page=page, has_next=has_next,
        actions=dashboard_actions(conn, g.actor, containers) if not module else None,
    )


@bp.get("/lookup")
@authorized()
def lookup():
    value = request.args.get("code", "").strip()
    conn = db.get()
    item = row(conn, "SELECT * FROM containers WHERE qr=? OR label=?", (value, value.upper()))
    check_container_access(conn, item, active_cycle(conn, item["id"]))
    return redirect(url_for("web.container", qr=item["qr"]))


def check_container_access(conn, item, cycle):
    if g.actor["role"] != "petugas_unit":
        return
    loan = active_loan_item(conn, item["id"])
    if not cycle or not (eligible(conn, cycle["id"]) or (loan and loan["unit_id"] == g.actor["unit_id"])):
        abort(404, "Kontainer tidak tersedia untuk unit ini.")


@bp.get("/c/<qr>")
@authorized()
def container(qr):
    conn = db.get()
    item = row(conn, "SELECT * FROM containers WHERE qr=?", (qr,))
    cycle = active_cycle(conn, item["id"])
    batch = decision = None
    batch_members = []
    if cycle and g.actor["role"] in TRUSTED:
        batch = sterilization.for_cycle(conn, cycle["id"])
        if batch:
            batch_members = sterilization.members(conn, batch["id"])
        decision = conn.execute("SELECT * FROM qc_decisions WHERE cycle_id=?", (cycle["id"],)).fetchone()
    check_container_access(conn, item, cycle)
    previous = []
    compositions = {}
    previous_batches = {}
    history_before = None
    older = False
    if g.actor["role"] in TRUSTED:
        raw_before = request.args.get("sebelum")
        history_before = numeric_id(raw_before) if raw_before else None
        boundary = " AND sequence<?" if history_before else ""
        previous = conn.execute(
            "SELECT * FROM cycles WHERE container_id=? AND closed_at IS NOT NULL"
            + boundary + " ORDER BY sequence DESC LIMIT 26",
            (item["id"], history_before) if history_before else (item["id"],),
        ).fetchall()
        older = len(previous) > 25
        previous = previous[:25]
        compositions = snapshots(conn, [old["id"] for old in previous])
        previous_batches = sterilization.history(conn, [old["id"] for old in previous])
    current = snapshot(conn, cycle["id"]) if cycle else []
    set_name = row(conn, "SELECT name FROM templates WHERE id=?",
                   (cycle["template_id"] if cycle else item["template_id"],))["name"]
    planned = template_items(conn, cycle["template_id"]) if cycle and cycle["state"] == "DRAFT" else []
    catalog = []
    custom_quantities = {}
    if g.actor["role"] == "petugas_cssd" and cycle and cycle["state"] == "DRAFT":
        catalog = conn.execute("SELECT id, name FROM instruments ORDER BY name").fetchall()
        if cycle["template_id"] != item["template_id"]:
            custom_quantities = {entry["instrument_id"]: entry["expected"] for entry in planned}
    return_item = active_loan_item(conn, item["id"]) if g.actor["role"] == "petugas_cssd" else None
    preparation = None
    if cycle and g.actor["role"] == "petugas_cssd":
        preparation = conn.execute("SELECT id FROM loans WHERE prepared_cycle_id=?", (cycle["id"],)).fetchone()
    variant = bool(cycle and availability(conn, cycle["id"])["variation"])
    return render_template(
        "container.html", item=item, cycle=cycle, current=current, planned=planned,
        previous=previous, compositions=compositions, return_item=return_item, variant=variant,
        older=older, history_before=history_before,
        preparation=preparation,
        batch=batch, batch_members=batch_members, decision=decision, set_name=set_name,
        previous_batches=previous_batches,
        catalog=catalog, custom_quantities=custom_quantities,
    )


@bp.get("/c/<qr>/qr.png")
@authorized(*TRUSTED)
def qr_image(qr):
    import cv2
    import numpy as np

    item = row(db.get(), "SELECT qr FROM containers WHERE qr=?", (qr,))
    path = url_for("web.container", qr=item["qr"], _external=True)
    matrix = cv2.QRCodeEncoder_create().encode(path)
    padded = np.pad(matrix, 4, constant_values=255)
    enlarged = cv2.resize(padded, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
    success, png = cv2.imencode(".png", enlarged)
    if not success:
        abort(503, "Label QR belum dapat dibuat.")
    return send_file(BytesIO(png.tobytes()), mimetype="image/png", max_age=0)


@bp.post("/c/<qr>/start")
@authorized("petugas_cssd")
def start_cycle(qr):
    def apply(conn, actor):
        item = row(conn, "SELECT * FROM containers WHERE qr=?", (qr,))
        identifier, number = open_cycle(conn, actor, item["id"], item["template_id"])
        return identifier, url_for("web.container", qr=qr), "Buka siklus setting", {"sequence": number, "container": item["id"]}
    return mutation("CREATE_CYCLE", "cycle", apply)


def open_cycle(conn, actor, container_id, template_id):
    if active_cycle(conn, container_id):
        abort(409, "Kontainer masih memiliki siklus aktif.")
    number = conn.execute(
        "SELECT COALESCE(MAX(sequence),0)+1 AS next_number FROM cycles WHERE container_id=?", (container_id,),
    ).fetchone()["next_number"]
    identifier = insert(conn, """
        INSERT INTO cycles(container_id,template_id,sequence,state,created_by)
        VALUES (?,?,?,'DRAFT',?)
    """, (container_id, template_id, number, actor))
    return identifier, number


CYCLE_ACTIONS = {
    "composition": {"DRAFT"},
    "revise-composition": {"VERIFIED"},
    "verify": {"DRAFT"},
    "pack": {"VERIFIED"},
    "batch-start": {"PACKAGED"},
    "batch-complete": {"PROCESSING"},
    "qc": {"QC_PENDING"},
    "decontaminate": {"DIRTY_RECEIVED"},
}


@bp.post("/batches")
@authorized("petugas_cssd")
def create_batch():
    def apply(conn, actor):
        cycle_ids = [numeric_id(value) for value in request.form.getlist("cycles")]
        if not cycle_ids or len(cycle_ids) != len(set(cycle_ids)):
            abort(400, "Pilih kontainer yang berbeda untuk batch.")
        reference = text(request.form, "reference", "Referensi batch")
        batch_id = sterilization.start(conn, actor, cycle_ids, reference)
        return batch_id, url_for("web.dashboard", modul="sterilisasi", status="PROCESSING"), "Mulai batch", {
            "cycles": cycle_ids, "before": "PACKAGED", "after": "PROCESSING",
        }
    return mutation("BATCH_START", "batch", apply)


@bp.post("/cycles/<int:cycle_id>/<action>")
@authorized("petugas_cssd")
def cycle_action(cycle_id, action):
    if action not in CYCLE_ACTIONS:
        abort(404)
    if action == "qc" and not g.actor["can_release_qc"]:
        abort(403, "Akun ini belum memiliki kewenangan keputusan QC.")
    states = CYCLE_ACTIONS[action]

    def apply(conn, actor):
        cycle = row(conn, """
            SELECT cy.*, c.qr, c.label, c.template_id AS default_template_id
            FROM cycles cy JOIN containers c ON c.id=cy.container_id WHERE cy.id=?
        """, (cycle_id,))
        require_state(cycle, states)
        if cycle["closed_at"] is not None:
            abort(409, "Siklus sudah ditutup. Buka siklus aktif untuk melanjutkan.")
        reason = action
        details = {}
        template_ref = request.form.get("template_id")
        if action in {"composition", "verify"} and (
            template_ref is not None or action == "composition" or cycle["template_id"] != cycle["default_template_id"]
        ) and template_ref != str(cycle["template_id"]):
            abort(409, "Komposisi sudah berubah. Muat ulang dan periksa kembali daftar instrumen.")
        if action == "composition":
            mode = request.form.get("mode")
            if mode == "custom":
                template_id = create_template_version(conn, f"Set khusus {cycle['label']}", request.form)
            elif mode == "standard":
                template_id = cycle["default_template_id"]
            else:
                abort(400, "Pilih komposisi khusus atau template standar.")
            conn.execute("UPDATE cycles SET template_id=? WHERE id=?", (template_id, cycle_id))
            details.update(previous_template=cycle["template_id"], template=template_id, mode=mode)
            new_state = "DRAFT"
        elif action == "revise-composition":
            if cycle["template_id"] == cycle["default_template_id"] or not availability(conn, cycle_id)["variation"]:
                abort(409, "Revisi ini tersedia untuk komposisi khusus yang memiliki selisih.")
            linked = conn.execute("SELECT id FROM loans WHERE prepared_cycle_id=?", (cycle_id,)).fetchone()
            mode = request.form.get("mode")
            template_id = cycle["template_id"]
            if mode == "use-count":
                if linked:
                    abort(409, "Set ini terkait permintaan unit. Hitung ulang sesuai rencana yang diajukan.")
                counted = [
                    (item["instrument_id"], item["verified"])
                    for item in snapshot(conn, cycle_id) if item["verified"] > 0
                ]
                if not counted:
                    abort(400, "Rencana baru harus memuat minimal satu alat.")
                template_id = save_template_version(conn, f"Set khusus {cycle['label']}", counted)
            elif mode != "recount":
                abort(400, "Pilih hitung ulang atau gunakan hitungan sebagai rencana baru.")
            conn.execute("UPDATE cycles SET closed_at=CURRENT_TIMESTAMP WHERE id=?", (cycle_id,))
            new_cycle, sequence = open_cycle(conn, actor, cycle["container_id"], template_id)
            if linked:
                conn.execute("UPDATE loans SET prepared_cycle_id=? WHERE id=?", (new_cycle, linked["id"]))
            return new_cycle, url_for("web.container", qr=cycle["qr"]), "Koreksi komposisi set khusus", {
                "previous_cycle": cycle_id, "sequence": sequence, "previous_template": cycle["template_id"],
                "template": template_id, "mode": mode, "before": "VERIFIED", "after": "DRAFT",
            }
        elif action == "verify":
            planned = template_items(conn, cycle["template_id"])
            if not planned:
                abort(409, "Template belum memiliki komposisi.")
            values = quantities(request.form, planned)
            conn.executemany("INSERT INTO cycle_items VALUES(?,?,?,?,?,?)", [
                (cycle_id, item["instrument_id"], item["name"], item["expected"], actual, note)
                for item, actual, note in values
            ])
            conn.execute("UPDATE cycles SET verified_at=CURRENT_TIMESTAMP, verified_by=? WHERE id=?", (actor, cycle_id))
            details["quantities"] = {item["instrument_id"]: actual for item, actual, _ in values}
            new_state = "VERIFIED"
        elif action == "pack":
            if availability(conn, cycle_id)["variation"]:
                abort(409, "Ada selisih komposisi. Alur demo menahan kontainer untuk peninjauan.")
            new_state = "PACKAGED"
        elif action == "batch-start":
            reference = text(request.form, "reference", "Referensi proses")
            batch_id = sterilization.start(conn, actor, [cycle_id], reference)
            return batch_id, url_for("web.container", qr=cycle["qr"]), reason, {
                "cycles": [cycle_id], "before": cycle["state"], "after": "PROCESSING",
            }
        elif action == "batch-complete":
            evidence = request.form.get("process_evidence", "").strip()
            if len(evidence) > 200:
                abort(400, "Referensi bukti proses maksimal 200 karakter.")
            batch_id, cycle_ids = sterilization.complete(conn, cycle_id, evidence or None)
            return batch_id, url_for("web.container", qr=cycle["qr"]), reason, {
                "cycles": cycle_ids, "before": cycle["state"], "after": "QC_PENDING",
            }
        elif action == "qc":
            outcome = request.form.get("outcome")
            if outcome not in {"RELEASE", "REJECT", "QUARANTINE"}:
                abort(400, "Pilih keputusan QC.")
            evidence = text(request.form, "evidence", "Referensi bukti simulasi")
            if outcome == "RELEASE" and availability(conn, cycle_id)["variation"]:
                abort(409, "Komposisi berbeda dari template simulasi.")
            conn.execute("INSERT INTO qc_decisions(cycle_id,outcome,evidence,officer_id) VALUES(?,?,?,?)", (cycle_id, outcome, evidence, actor))
            reason = outcome
            new_state = {"RELEASE": "AVAILABLE", "REJECT": "REJECTED", "QUARANTINE": "QUARANTINED"}[outcome]
        else:
            reason = text(request.form, "reason", "Referensi selesai dekontaminasi simulasi")
            conn.execute("UPDATE cycles SET closed_at=CURRENT_TIMESTAMP WHERE id=?", (cycle_id,))
            new_state = "DECONTAMINATED"
        conn.execute("UPDATE cycles SET state=? WHERE id=?", (new_state, cycle_id))
        details.update(before=cycle["state"], after=new_state)
        return cycle_id, url_for("web.container", qr=cycle["qr"]), reason, details

    return mutation(action.upper().replace("-", "_"), "batch" if action.startswith("batch-") else "cycle", apply)


def loan_access(conn, loan_id):
    loan = row(conn, """
        SELECT l.*, u.name AS unit, r.name AS requester_name, w.name AS warehouse_name,
               p.name AS recipient_name
        FROM loans l JOIN units u ON u.id=l.unit_id JOIN users r ON r.id=l.requester
        LEFT JOIN users w ON w.id=l.handed_over_by LEFT JOIN users p ON p.id=l.received_by
        WHERE l.id=?
    """, (loan_id,))
    if g.actor["role"] == "petugas_unit" and loan["unit_id"] != g.actor["unit_id"]:
        abort(404)
    return loan


def stock_catalog(conn, cycle_ids=None):
    where = AVAILABLE_STOCK
    if cycle_ids is not None:
        where += " AND cy.id IN (" + ",".join("?" for _ in cycle_ids) + ")"
    return conn.execute(f"""
        WITH stock AS ({ACTIVE_CONTAINER_STOCK} WHERE {where})
        SELECT stock.*, ci.instrument_id, ci.name AS instrument_name
        FROM stock {SINGLE_INSTRUMENT} ORDER BY stock.label
    """, tuple(cycle_ids or ())).fetchall()


def loan_packages(conn, codes):
    if not 1 <= len(codes) <= 20 or len(set(codes)) != len(codes):
        abort(400, "Sertakan 1-20 kontainer berbeda.")
    placeholders = ",".join("?" for _ in codes)
    labels = tuple(code.upper() for code in codes)
    packages = conn.execute(f"""
        SELECT c.id, c.label, c.qr, CASE WHEN ({AVAILABLE_STOCK}) THEN cy.id END AS cycle_id
        FROM containers c LEFT JOIN cycles cy ON cy.container_id=c.id AND cy.closed_at IS NULL
        WHERE c.qr IN ({placeholders}) OR c.label IN ({placeholders})
    """, (*codes, *labels)).fetchall()
    by_qr = {item["qr"]: item for item in packages}
    by_label = {item["label"]: item for item in packages}
    validated = []
    for code in codes:
        item = by_qr.get(code) or by_label.get(code.upper())
        if item is None:
            abort(404, "Kontainer tidak ditemukan.")
        if item["cycle_id"] is None:
            abort(409, f"{item['label']} belum tersedia.")
        validated.append((item["id"], item["cycle_id"]))
    if len({item_id for item_id, _ in validated}) != len(validated):
        abort(400, "Satu kontainer terdaftar lebih dari sekali.")
    return validated


@bp.route("/loans/needs", methods=["GET", "POST"])
@authorized("petugas_unit")
def new_need():
    custom = request.args.get("jenis") == "khusus"
    if request.method == "GET":
        return render_template("loan_needs.html", options=loan_needs.catalog(db.get(), custom), custom=custom)

    def apply(conn, actor):
        lines = loan_needs.requested_lines(request.form, loan_needs.catalog(conn, custom))
        needed_at = request.form.get("needed_at", "")
        if needed_at:
            try:
                needed_at = datetime.strptime(needed_at, "%Y-%m-%dT%H:%M").replace(tzinfo=ZoneInfo("Asia/Jakarta"))
            except ValueError:
                abort(400, "Pilih tanggal dan jam kebutuhan yang valid.")
            needed_at = needed_at.astimezone(timezone.utc).isoformat()
        unit = g.actor["unit_id"]
        loan_id = insert(conn, """
            INSERT INTO loans(unit_id,requester,state,needed_at) VALUES(?,?,'REQUESTED',?)
        """, (unit, actor, needed_at or None))
        conn.executemany("""
            INSERT INTO loan_needs(loan_id,kind,item_name,instrument_id,quantity) VALUES(?,?,?,?,?)
        """, [(loan_id, *line) for line in lines])
        return loan_id, url_for("web.loan_detail", loan_id=loan_id), "Permintaan berdasarkan kebutuhan", {
            "unit": unit, "needs": lines, "needed_at": needed_at or None, "after": "REQUESTED",
        }
    return mutation("REQUEST_LOAN", "loan", apply)


@bp.route("/loans/new", methods=["GET", "POST"])
@authorized("petugas_unit")
def new_loan():
    if request.method == "GET":
        stock = stock_catalog(db.get())
        sets = []
        groups = {}
        for item in stock:
            if item["instrument_id"] is None:
                sets.append(item)
            else:
                group = groups.setdefault(item["instrument_id"], {
                    "name": db.instrument_display_name(item["instrument_name"]),
                    "packages": [],
                })
                group["packages"].append(item)
        instruments = sorted(groups.values(), key=lambda group: group["name"].casefold())
        return render_template("new_loan.html", sets=sets, instruments=instruments)

    def apply(conn, actor):
        validated = loan_packages(conn, request.form.getlist("containers"))
        unit = g.actor["unit_id"]
        loan_id = insert(conn, "INSERT INTO loans(unit_id,requester,state) VALUES(?,?,'REQUESTED')", (unit, actor))
        conn.executemany("INSERT INTO loan_items(loan_id,container_id,cycle_id) VALUES(?,?,?)",
                         [(loan_id, item_id, cycle_id) for item_id, cycle_id in validated])
        return loan_id, url_for("web.loan_detail", loan_id=loan_id), "Permintaan dari unit demo", {
            "unit": unit, "items": validated, "after": "REQUESTED",
        }
    return mutation("REQUEST_LOAN", "loan", apply)


@bp.get("/loans/<int:loan_id>")
@authorized("petugas_unit", *TRUSTED)
def loan_detail(loan_id):
    conn = db.get()
    loan = loan_access(conn, loan_id)
    needs = loan_needs.for_loan(conn, loan_id)
    items = loan_items(conn, loan_id)
    recipients = []
    candidates = []
    setting_containers = []
    needs_setting = False
    prepared = None
    if loan["prepared_cycle_id"]:
        prepared = row(conn, """
            SELECT cy.state, cy.closed_at, c.qr, c.label FROM cycles cy
            JOIN containers c ON c.id=cy.container_id WHERE cy.id=?
        """, (loan["prepared_cycle_id"],))
    if g.actor["role"] == "petugas_cssd" and loan["state"] == "PICKING":
        recipients = conn.execute("SELECT id,name FROM users WHERE unit_id=? AND role='petugas_unit'", (loan["unit_id"],)).fetchall()
        if needs:
            candidates = loan_needs.matching_stock(conn, needs, stock_catalog(conn))
            needs_setting = needs[0]["kind"] == "custom" and not candidates and can_prepare_custom(prepared)
            if needs_setting:
                setting_containers = conn.execute(CUSTOM_SETTING_CONTAINERS + " ORDER BY c.label").fetchall()
    return render_template("loan.html", loan=loan, items=items, needs=needs, candidates=candidates,
                           setting_containers=setting_containers, needs_setting=needs_setting, prepared=prepared,
                           selected_cycles={item["cycle_id"] for item in items}, recipients=recipients,
                           allocation=",".join(str(item["cycle_id"]) for item in items))


LOAN_ACTIONS = {
    "pick": ("petugas_cssd", "REQUESTED"),
    "allocate": ("petugas_cssd", "PICKING"),
    "handover": ("petugas_cssd", "PICKING"),
    "receive": ("petugas_unit", "HANDED_OVER"),
    "cancel": ("petugas_cssd", ("REQUESTED", "PICKING")),
}


def can_prepare_custom(cycle):
    return not cycle or cycle["closed_at"] is not None or cycle["state"] in {
        "REJECTED", "QUARANTINED", "EXPIRED", "BORROWED", "DIRTY_RECEIVED", "DISCREPANCY",
    }


CUSTOM_SETTING_CONTAINERS = """
    SELECT c.id,c.label,c.qr,cy.id AS draft_id,cy.sequence
    FROM containers c LEFT JOIN cycles cy ON cy.container_id=c.id AND cy.closed_at IS NULL
    WHERE (cy.id IS NULL OR (
        cy.state='DRAFT' AND cy.template_id=c.template_id AND cy.verified_at IS NULL
        AND NOT EXISTS (SELECT 1 FROM cycle_items ci WHERE ci.cycle_id=cy.id)
        AND NOT EXISTS (SELECT 1 FROM loans l WHERE l.prepared_cycle_id=cy.id)
    ))
"""


@bp.post("/loans/<int:loan_id>/prepare-custom")
@authorized("petugas_cssd")
def prepare_custom(loan_id):
    def apply(conn, actor):
        loan = loan_access(conn, loan_id)
        require_state(loan, {"PICKING"})
        needs = loan_needs.for_loan(conn, loan_id)
        if not needs or needs[0]["kind"] != "custom":
            abort(409, "Pengajuan ini tidak meminta set khusus.")
        if loan["prepared_cycle_id"]:
            cycle = row(conn, "SELECT state,closed_at FROM cycles WHERE id=?", (loan["prepared_cycle_id"],))
            if not can_prepare_custom(cycle):
                abort(409, "Persiapan set khusus sudah dimulai.")
        container_id = numeric_id(request.form.get("container"))
        item = conn.execute(CUSTOM_SETTING_CONTAINERS + " AND c.id=?", (container_id,)).fetchone()
        if item is None:
            abort(409, "Kontainer sudah tidak tersedia untuk setting permintaan ini. Muat ulang halaman.")
        template = save_template_version(conn, f"Set khusus {item['label']}", [
            (line["instrument_id"], line["quantity"]) for line in needs
        ])
        cycle_id, sequence = item["draft_id"], item["sequence"]
        if cycle_id is None:
            cycle_id, sequence = open_cycle(conn, actor, item["id"], template)
        else:
            conn.execute("UPDATE cycles SET template_id=? WHERE id=?", (template, cycle_id))
        conn.execute("UPDATE loans SET prepared_cycle_id=? WHERE id=?", (cycle_id, loan_id))
        return cycle_id, url_for("web.container", qr=item["qr"]), "Buka setting dari kebutuhan unit", {
            "loan": loan_id, "sequence": sequence, "container": item["id"], "template": template,
            "reused_draft": item["draft_id"] is not None,
        }
    return mutation("PREPARE_CUSTOM", "cycle", apply)


@bp.post("/loans/<int:loan_id>/<action>")
@authorized()
def loan_action(loan_id, action):
    if action not in LOAN_ACTIONS:
        abort(404)
    role, state = LOAN_ACTIONS[action]
    if g.actor["role"] != role:
        abort(403)

    def apply(conn, actor):
        loan = loan_access(conn, loan_id)
        require_state(loan, (state,) if isinstance(state, str) else state)
        details = {"before": loan["state"], "unit": loan["unit_id"]}
        reason = action
        if action == "pick":
            new_state = "PICKING"
        elif action == "allocate":
            needs = loan_needs.for_loan(conn, loan_id)
            if not needs:
                abort(409, "Pengajuan ini sudah memilih kontainer langsung.")
            validated = loan_packages(conn, request.form.getlist("containers"))
            available = stock_catalog(conn, [cycle_id for _, cycle_id in validated])
            matching = loan_needs.matching_stock(conn, needs, available)
            if len(matching) != len(validated) or not loan_needs.complete(needs, matching):
                abort(409, "Jenis atau jumlah kemasan belum sesuai permintaan.")
            conn.execute("DELETE FROM loan_items WHERE loan_id=?", (loan_id,))
            conn.executemany("INSERT INTO loan_items(loan_id,container_id,cycle_id) VALUES(?,?,?)",
                             [(loan_id, item_id, cycle_id) for item_id, cycle_id in validated])
            details["items"] = validated
            new_state = "PICKING"
        elif action == "cancel":
            reason = text(request.form, "reason", "Alasan pembatalan")
            new_state = "CANCELLED"
        elif action == "handover":
            if request.form.get("physical_check") != "yes":
                abort(400, "Gudang wajib mengonfirmasi serah terima fisik.")
            recipient = row(conn, "SELECT id FROM users WHERE id=? AND unit_id=? AND role='petugas_unit'",
                            (numeric_id(request.form.get("recipient")), loan["unit_id"]))["id"]
            items = loan_items(conn, loan_id)
            if not items:
                abort(409, "Pilih dan simpan kemasan yang sesuai sebelum serah terima.")
            if loan_needs.for_loan(conn, loan_id) and request.form.get("allocation") != ",".join(
                str(item["cycle_id"]) for item in items
            ):
                abort(409, "Kemasan terpilih berubah. Muat ulang dan periksa kembali serah terima.")
            available = {item["cycle_id"] for item in stock_catalog(conn, [item["cycle_id"] for item in items])}
            for item in items:
                if item["cycle_id"] not in available:
                    abort(409, f"{item['label']} sudah tidak tersedia. Serah terima batal seluruhnya.")
            conn.execute("UPDATE loans SET handed_over_by=?,handed_over_at=CURRENT_TIMESTAMP,received_by=? WHERE id=?",
                         (actor, recipient, loan_id))
            conn.execute("UPDATE loan_items SET handed_at=CURRENT_TIMESTAMP WHERE loan_id=?", (loan_id,))
            conn.executemany("UPDATE cycles SET state='BORROWED' WHERE id=?", [(i["cycle_id"],) for i in items])
            details.update(recipient=recipient, cycles=[i["cycle_id"] for i in items])
            new_state = "HANDED_OVER"
        else:
            if loan["received_by"] != actor:
                abort(403, "Hanya penerima yang tercatat dapat mengonfirmasi.")
            if request.form.get("physical_check") != "yes":
                abort(400, "Konfirmasi penerimaan fisik wajib diisi.")
            conn.execute("UPDATE loans SET received_at=CURRENT_TIMESTAMP WHERE id=?", (loan_id,))
            new_state = "RECEIVED"
        conn.execute("UPDATE loans SET state=? WHERE id=?", (new_state, loan_id))
        details["after"] = new_state
        return loan_id, url_for("web.loan_detail", loan_id=loan_id), reason, details
    return mutation(action.upper(), "loan", apply)


@bp.post("/c/<qr>/return/<int:loan_item_id>")
@authorized("petugas_cssd")
def return_container(qr, loan_item_id):
    def apply(conn, actor):
        c = row(conn, "SELECT id FROM containers WHERE qr=?", (qr,))
        active = active_loan_item(conn, c["id"])
        if not active or active["id"] != loan_item_id:
            abort(409, "Transaksi pinjaman aktif berubah. Scan ulang kontainer.")
        if active["loan_state"] not in {"RECEIVED", "PARTIALLY_RETURNED"}:
            abort(409, "Penerima belum mengonfirmasi serah terima.")
        cycle_id, loan_id = active["cycle_id"], active["loan_id"]
        cycle = row(conn, "SELECT state FROM cycles WHERE id=?", (cycle_id,))
        require_state(cycle, {"BORROWED"})
        expected_items = snapshot(conn, cycle_id)
        if not expected_items:
            abort(409, "Komposisi siklus serah terima tidak ditemukan.")
        actual = quantities(request.form, expected_items, returning=True)
        return_id = insert(conn, "INSERT INTO returns(loan_id,loan_item_id,cycle_id,received_by) VALUES(?,?,?,?)",
                           (loan_id, loan_item_id, cycle_id, actor))
        conn.executemany("INSERT INTO return_items VALUES(?,?,?,?,?,?)", [
            (return_id, cycle_id, item["instrument_id"], item["verified"], qty, note)
            for item, qty, note in actual
        ])
        mismatches = [
            {"instrument": item["instrument_id"], "expected": item["verified"], "actual": qty}
            for item, qty, _ in actual if qty != item["verified"]
        ]
        state = "DISCREPANCY" if mismatches else "DIRTY_RECEIVED"
        case_id = None
        if mismatches:
            case_id = insert(conn, "INSERT INTO discrepancy_cases(return_id,status) VALUES(?,'OPEN')", (return_id,))
            conn.execute("INSERT INTO notifications(case_id,target_role) VALUES(?,?)", (case_id, "supervisor"))
        conn.execute("UPDATE cycles SET state=? WHERE id=?", (state, cycle_id))
        conn.execute("UPDATE loan_items SET returned_at=CURRENT_TIMESTAMP WHERE id=?", (loan_item_id,))
        outstanding = conn.execute("SELECT 1 FROM loan_items WHERE loan_id=? AND returned_at IS NULL", (loan_id,)).fetchone()
        loan_state = "PARTIALLY_RETURNED" if outstanding else "RETURNED"
        conn.execute("UPDATE loans SET state=? WHERE id=?", (loan_state, loan_id))
        return return_id, url_for("web.return_detail", return_id=return_id), "Penerimaan fisik di area dekontaminasi demo", {
            "loan": loan_id, "loan_item": loan_item_id, "cycle": cycle_id, "case": case_id,
            "differences": mismatches, "before": cycle["state"], "after": state, "loan_state": loan_state,
        }
    return mutation("VERIFY_RETURN", "return", apply)


def recorded_return_items(conn, return_id):
    items = conn.execute("""
        SELECT ri.expected, ri.actual, ri.condition_note, ci.name
        FROM return_items ri JOIN cycle_items ci
        ON ci.cycle_id=ri.cycle_id AND ci.instrument_id=ri.instrument_id
        WHERE ri.return_id=? ORDER BY ci.name, ri.instrument_id
    """, (return_id,)).fetchall()
    return [dict(item, name=db.instrument_display_name(item["name"])) for item in items]


@bp.get("/returns/<int:return_id>")
@authorized(*TRUSTED)
def return_detail(return_id):
    conn = db.get()
    record = row(conn, """
        SELECT r.*, c.label, cy.sequence, staff.name AS receiver, dc.id AS case_id
        FROM returns r
        JOIN cycles cy ON cy.id=r.cycle_id JOIN containers c ON c.id=cy.container_id
        JOIN users staff ON staff.id=r.received_by
        LEFT JOIN discrepancy_cases dc ON dc.return_id=r.id
        WHERE r.id=?
    """, (return_id,))
    loan = loan_access(conn, record["loan_id"])
    return render_template(
        "return.html", record=record, loan=loan, items=recorded_return_items(conn, return_id),
    )


@bp.get("/cases/<int:case_id>")
@authorized("supervisor")
def case_detail(case_id):
    conn = db.get()
    case = row(conn, """
        SELECT d.*, r.loan_id, r.cycle_id, r.received_at, c.label, cy.sequence,
               receiver.name AS receiver, resolver.name AS resolver
        FROM discrepancy_cases d JOIN returns r ON r.id=d.return_id
        JOIN cycles cy ON cy.id=r.cycle_id JOIN containers c ON c.id=cy.container_id
        JOIN users receiver ON receiver.id=r.received_by
        LEFT JOIN users resolver ON resolver.id=d.resolved_by
        WHERE d.id=?
    """, (case_id,))
    loan = loan_access(conn, case["loan_id"])
    items = [item for item in recorded_return_items(conn, case["return_id"]) if item["expected"] != item["actual"]]
    events = conn.execute("""
        SELECT a.action, a.reason, a.created_at, COALESCE(a.actor_username,u.username) AS username
        FROM audit_events a JOIN users u ON u.id=a.actor_id
        WHERE a.entity='case' AND a.entity_id=? AND a.action IN ('INVESTIGATE','RESOLVE')
        ORDER BY a.id
    """, (case_id,)).fetchall()
    return render_template("case.html", case=case, loan=loan, items=items, events=events)


@bp.post("/cases/<int:case_id>/<action>")
@authorized("supervisor")
def case_action(case_id, action):
    if action not in {"investigate", "resolve"}:
        abort(404)

    def apply(conn, actor):
        case = row(conn, """
            SELECT d.*, r.cycle_id FROM discrepancy_cases d JOIN returns r ON r.id=d.return_id
            WHERE d.id=?
        """, (case_id,))
        reason = text(request.form, "reason", "Catatan investigasi")
        if action == "investigate":
            require_status = "OPEN"
            status = "INVESTIGATING"
        else:
            require_status = "INVESTIGATING"
            status = "RESOLVED"
        if case["status"] != require_status:
            abort(409, "Status investigasi berubah.")
        conn.execute("UPDATE discrepancy_cases SET status=? WHERE id=?", (status, case_id))
        if action == "resolve":
            cycle = row(conn, "SELECT state FROM cycles WHERE id=?", (case["cycle_id"],))
            require_state(cycle, {"DISCREPANCY"})
            conn.execute("""
                UPDATE discrepancy_cases SET resolution=?,resolved_by=?,resolved_at=CURRENT_TIMESTAMP WHERE id=?
            """, (reason, actor, case_id))
            conn.execute("UPDATE cycles SET state='DIRTY_RECEIVED' WHERE id=?", (case["cycle_id"],))
        return case_id, url_for("web.case_detail", case_id=case_id), reason, {
            "before": case["status"], "after": status, "cycle": case["cycle_id"],
            "cycle_after": "DIRTY_RECEIVED" if action == "resolve" else "DISCREPANCY",
        }
    return mutation(action.upper(), "case", apply)


AUDIT_MODULES = {
    "setting": ("CREATE_CYCLE", "PREPARE_CUSTOM", "COMPOSITION", "REVISE_COMPOSITION", "VERIFY", "PACK"),
    "sterilisasi": ("BATCH_START", "BATCH_COMPLETE"),
    "qc": ("QC",),
    "gudang": ("PICK", "ALLOCATE", "HANDOVER", "CANCEL"),
    "dekontaminasi": ("VERIFY_RETURN", "DECONTAMINATE"),
    "unit": ("REQUEST_LOAN", "RECEIVE"),
    "supervisor": ("INVESTIGATE", "RESOLVE"),
    "admin": ("CREATE_MASTER", "CREATE_USER", "SET_QC_PERMISSION", "RENAME_DEMO_CATALOG"),
}


@bp.get("/audit")
@authorized("admin", "supervisor")
def audit():
    conn = db.get()
    filters = {name: request.args.get(name, "").strip() for name in ("actor", "modul", "container", "day")}
    where = []
    params = []
    if filters["actor"]:
        where.append("a.actor_id=?")
        params.append(numeric_id(filters["actor"]))
    if filters["modul"]:
        actions = AUDIT_MODULES.get(filters["modul"])
        if not actions:
            abort(400, "Modul audit tidak valid.")
        where.append("a.action IN (" + ",".join("?" for _ in actions) + ")")
        params.extend(actions)
    if filters["container"]:
        where.append("""EXISTS (
            SELECT 1 FROM containers c WHERE c.label=? AND (
                (a.entity='container' AND a.entity_id=c.id)
                OR (a.entity='cycle' AND EXISTS (
                    SELECT 1 FROM cycles cy WHERE cy.id=a.entity_id AND cy.container_id=c.id))
                OR (a.entity='batch' AND EXISTS (
                    SELECT 1 FROM batch_cycles bc JOIN cycles cy ON cy.id=bc.cycle_id
                    WHERE bc.batch_id=a.entity_id AND cy.container_id=c.id))
                OR (a.entity='loan' AND EXISTS (
                    SELECT 1 FROM loan_items li WHERE li.loan_id=a.entity_id AND li.container_id=c.id))
                OR (a.entity='return' AND EXISTS (
                    SELECT 1 FROM returns r JOIN loan_items li ON li.id=r.loan_item_id
                    WHERE r.id=a.entity_id AND li.container_id=c.id))
                OR (a.entity='case' AND EXISTS (
                    SELECT 1 FROM discrepancy_cases d JOIN returns r ON r.id=d.return_id
                    JOIN loan_items li ON li.id=r.loan_item_id WHERE d.id=a.entity_id AND li.container_id=c.id))
            )
        )""")
        params.append(filters["container"].upper())
    if filters["day"]:
        start, end = report_bounds(filters["day"])
        where.append("a.created_at>=? AND a.created_at<?")
        params.extend((start, end))
    sql = """
        SELECT a.*, COALESCE(a.actor_username, u.username) AS username,
               cy.id AS related_cycle, c.label AS container_label,
               COALESCE(l.id, r.loan_id) AS related_loan
        FROM audit_events a JOIN users u ON u.id=a.actor_id
        LEFT JOIN discrepancy_cases d ON a.entity='case' AND d.id=a.entity_id
        LEFT JOIN returns r ON (a.entity='return' AND r.id=a.entity_id) OR r.id=d.return_id
        LEFT JOIN cycles cy ON (a.entity='cycle' AND cy.id=a.entity_id) OR cy.id=r.cycle_id
        LEFT JOIN containers c ON c.id=cy.container_id OR (a.entity='container' AND c.id=a.entity_id)
        LEFT JOIN loans l ON a.entity='loan' AND l.id=a.entity_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    events = conn.execute(sql + " ORDER BY a.id DESC LIMIT 200", params).fetchall()
    action_modules = {action: module for module, actions in AUDIT_MODULES.items() for action in actions}
    return render_template(
        "audit.html", events=events, filters=filters, modules=AUDIT_MODULES, action_modules=action_modules,
        actors=conn.execute("SELECT id, username FROM users ORDER BY username").fetchall(),
    )


@bp.get("/accounts")
@authorized("admin")
def accounts():
    conn = db.get()
    return render_template(
        "accounts.html", email_login=bool(current_app.config["SUPABASE_URL"]),
        units=conn.execute("SELECT id, name FROM units ORDER BY id").fetchall(),
        accounts=conn.execute("""
            SELECT u.id, u.username, u.name, u.role, u.can_release_qc, n.name AS unit
            FROM users u JOIN units n ON n.id=u.unit_id ORDER BY u.username
        """).fetchall(),
    )


@bp.post("/accounts")
@authorized("admin")
def create_account():
    if current_app.config["SUPABASE_URL"]:
        abort(409, "Buat identitas di Supabase Auth dan kaitkan ke profil SteriTrack.")
    def apply(conn, actor):
        username = text(request.form, "username", "Akun", 50)
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", username):
            abort(400, "Gunakan huruf kecil, angka, titik, garis bawah, atau tanda hubung untuk akun.")
        name = text(request.form, "name", "Nama petugas", 80)
        role = request.form.get("role")
        if role not in ROLE_LABELS:
            abort(400, "Peran tidak valid.")
        password = request.form.get("password", "")
        if not 12 <= len(password) <= 200 or password != password.strip():
            abort(400, "Sandi harus 12–200 karakter tanpa spasi di awal atau akhir.")
        unit_id = numeric_id(request.form.get("unit"))
        row(conn, "SELECT id FROM units WHERE id=?", (unit_id,))
        user_id = insert(conn, """
            INSERT INTO users(username,name,password_hash,unit_id,role) VALUES(?,?,?,?,?)
        """, (username, name, generate_password_hash(password), unit_id, role))
        return user_id, url_for("web.accounts"), "Akun petugas dibuat", {
            "username": username, "role": role, "unit": unit_id,
        }

    return mutation("CREATE_USER", "user", apply)


@bp.post("/accounts/<int:user_id>/qc")
@authorized("admin")
def account_qc(user_id):
    def apply(conn, actor):
        account = row(conn, "SELECT role,can_release_qc FROM users WHERE id=?", (user_id,))
        if account["role"] != "petugas_cssd":
            abort(409, "Izin QC hanya tersedia untuk akun Petugas CSSD.")
        value = request.form.get("can_release_qc")
        if value not in {"0", "1"}:
            abort(400, "Pilih status izin QC.")
        reason = text(request.form, "reason", "Dasar perubahan kewenangan")
        conn.execute("UPDATE users SET can_release_qc=? WHERE id=?", (int(value), user_id))
        return user_id, url_for("web.accounts"), reason, {
            "permission": "can_release_qc", "before": account["can_release_qc"], "after": int(value),
        }

    return mutation("SET_QC_PERMISSION", "user", apply)


@bp.route("/master", methods=["GET"])
@authorized("admin")
def master():
    conn = db.get()
    return render_template(
        "master.html",
        instruments=conn.execute("SELECT * FROM instruments ORDER BY name").fetchall(),
        templates=conn.execute("SELECT * FROM templates ORDER BY name,version").fetchall(),
        containers=conn.execute("""
            SELECT c.*, t.name, t.version FROM containers c JOIN templates t ON t.id=c.template_id ORDER BY c.label
        """).fetchall(),
    )


def create_template_version(conn, name, form):
    entries = conn.execute("SELECT id FROM instruments").fetchall()
    selected = []
    for item in entries:
        values = form.getlist(f"qty_{item['id']}")
        if len(values) > 1:
            abort(400, "Isi satu jumlah per jenis instrumen.")
        value = values[0].strip() if values else ""
        if not value:
            continue
        if not re.fullmatch(r"[0-9]{1,5}", value) or int(value) < 1:
            abort(400, "Komposisi template harus berupa jumlah positif.")
        selected.append((item["id"], int(value)))
    if not selected:
        abort(400, "Isi sedikitnya satu jenis instrumen.")
    return save_template_version(conn, name, selected)


def save_template_version(conn, name, selected):
    version = conn.execute(
        "SELECT COALESCE(MAX(version),0)+1 AS next_version FROM templates WHERE name=?", (name,),
    ).fetchone()["next_version"]
    identifier = insert(conn, "INSERT INTO templates(name,version) VALUES(?,?)", (name, version))
    conn.executemany("INSERT INTO template_items VALUES(?,?,?)", [
        (identifier, instrument_id, qty) for instrument_id, qty in selected
    ])
    return identifier


@bp.post("/master/<kind>")
@authorized("admin")
def create_master(kind):
    if kind not in {"instrument", "template", "container"}:
        abort(404)

    def apply(conn, actor):
        if kind == "instrument":
            name = text(request.form, "name", "Nama instrumen", 80)
            identifier = insert(conn, "INSERT INTO instruments(name) VALUES(?)", (name,))
        elif kind == "template":
            name = text(request.form, "name", "Nama set", 80)
            identifier = create_template_version(conn, name, request.form)
        else:
            name = text(request.form, "label", "Label kontainer", 20).upper()
            if not re.fullmatch(r"C-[0-9]{1,16}", name):
                abort(400, "Format label demo adalah C- diikuti angka.")
            template = row(conn, "SELECT id FROM templates WHERE id=?", (numeric_id(request.form.get("template")),))
            identifier = insert(conn, "INSERT INTO containers(label,qr,template_id) VALUES(?,?,?)",
                                (name, secrets.token_urlsafe(18), template["id"]))
        return identifier, url_for("web.master"), "Registrasi master demo", {}

    return mutation("CREATE_MASTER", kind, apply)


def report_bounds(day):
    try:
        start = datetime.combine(date.fromisoformat(day), time.min, ZoneInfo("Asia/Jakarta"))
        return tuple(dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                     for dt in (start, start + timedelta(days=1)))
    except (ValueError, OverflowError):
        abort(400, "Tanggal tidak valid.")


def report_filters(conn):
    day = request.args.get("day", datetime.now(ZoneInfo("Asia/Jakarta")).date().isoformat())
    bounds = report_bounds(day)
    raw_unit = request.args.get("unit", "")
    unit = row(conn, "SELECT id,name FROM units WHERE id=?", (numeric_id(raw_unit),)) if raw_unit else None
    return date.fromisoformat(day), bounds, unit


def report_handovers(conn, bounds, unit_id):
    return conn.execute("""
        SELECT l.id, l.state, l.handed_over_at, u.name AS unit,
               (SELECT COUNT(*) FROM loan_items li WHERE li.loan_id=l.id AND li.handed_at IS NOT NULL) AS container_count
        FROM loans l JOIN units u ON u.id=l.unit_id
        WHERE l.handed_over_at>=? AND l.handed_over_at<? AND (CAST(? AS INTEGER) IS NULL OR l.unit_id=?)
        ORDER BY l.handed_over_at DESC, l.id DESC
    """, (*bounds, unit_id, unit_id)).fetchall()


def report_inventory(conn):
    return conn.execute("""
        SELECT state, count(*) AS total FROM cycles WHERE closed_at IS NULL
        AND state IN ('AVAILABLE','BORROWED','QC_PENDING','REJECTED','QUARANTINED','DISCREPANCY')
        GROUP BY state ORDER BY state
    """).fetchall()


def report_outstanding(conn, unit_id):
    return conn.execute("""
        SELECT l.id AS loan_id, u.name AS unit, c.label, cy.sequence, li.handed_at, l.state
        FROM loan_items li
        JOIN loans l ON l.id=li.loan_id JOIN units u ON u.id=l.unit_id
        JOIN containers c ON c.id=li.container_id JOIN cycles cy ON cy.id=li.cycle_id
        WHERE li.handed_at IS NOT NULL AND li.returned_at IS NULL
          AND (CAST(? AS INTEGER) IS NULL OR l.unit_id=?)
        ORDER BY li.handed_at, li.id
    """, (unit_id, unit_id)).fetchall()


def report_open_cases(conn, unit_id):
    return conn.execute("""
        SELECT d.id, d.status, r.id AS return_id, l.id AS loan_id, r.received_at,
               u.name AS unit, c.label, cy.sequence
        FROM discrepancy_cases d JOIN returns r ON r.id=d.return_id
        JOIN loans l ON l.id=r.loan_id JOIN units u ON u.id=l.unit_id
        JOIN cycles cy ON cy.id=r.cycle_id JOIN containers c ON c.id=cy.container_id
        WHERE d.status IN ('OPEN','INVESTIGATING')
          AND (CAST(? AS INTEGER) IS NULL OR l.unit_id=?)
        ORDER BY r.received_at, d.id
    """, (unit_id, unit_id)).fetchall()


@bp.get("/reports.xlsx")
@authorized("supervisor")
def download_report():
    conn = db.get()
    day, bounds, unit = report_filters(conn)
    unit_id = unit["id"] if unit else None
    handovers = report_handovers(conn, bounds, unit_id)
    returns = conn.execute("""
        SELECT r.id AS return_id, r.loan_id, r.received_at, u.name AS unit,
               c.label, cy.sequence, ci.name AS instrument, ri.expected, ri.actual,
               dc.id AS case_id, dc.status AS case_status
        FROM returns r
        JOIN loans l ON l.id=r.loan_id JOIN units u ON u.id=l.unit_id
        JOIN cycles cy ON cy.id=r.cycle_id JOIN containers c ON c.id=cy.container_id
        JOIN return_items ri ON ri.return_id=r.id AND ri.cycle_id=r.cycle_id
        JOIN cycle_items ci ON ci.cycle_id=ri.cycle_id AND ci.instrument_id=ri.instrument_id
        LEFT JOIN discrepancy_cases dc ON dc.return_id=r.id
        WHERE r.received_at>=? AND r.received_at<? AND (CAST(? AS INTEGER) IS NULL OR l.unit_id=?)
        ORDER BY r.received_at DESC, r.id DESC, ci.name, ri.instrument_id
    """, (*bounds, unit_id, unit_id)).fetchall()
    workbook = write_workbook(
        day, unit["name"] if unit else "Semua unit", handovers, returns,
        report_inventory(conn), localtime, LOAN_STATUS_LABELS,
        outstanding=report_outstanding(conn, unit_id), open_cases=report_open_cases(conn, unit_id),
    )
    return send_file(
        workbook, as_attachment=True, download_name=f"laporan-steritrack-{day.isoformat()}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp.get("/reports")
@authorized("supervisor")
def reports():
    conn = db.get()
    day, bounds, selected_unit = report_filters(conn)
    unit = selected_unit["id"] if selected_unit else None
    loans = report_handovers(conn, bounds, unit)
    inventory = report_inventory(conn)
    units = conn.execute("SELECT id, name FROM units ORDER BY id").fetchall()
    return render_template(
        "reports.html", loans=loans, inventory=inventory, units=units, day=day.isoformat(), unit=unit,
        outstanding=report_outstanding(conn, unit), open_cases=report_open_cases(conn, unit),
    )


@bp.get("/api/container-preview")
@authorized("petugas_unit")
def container_preview():
    code = text(request.args, "code", "Kode kontainer", 100)
    conn = db.get()
    item = row(conn, "SELECT id,qr,label FROM containers WHERE qr=? OR label=?", (code, code.upper()))
    cycle = active_cycle(conn, item["id"])
    if not cycle or not eligible(conn, cycle["id"]):
        abort(409, "Kontainer belum tersedia.")
    stock = row(conn, f"""
        WITH stock AS ({ACTIVE_CONTAINER_STOCK} WHERE cy.id=?)
        SELECT stock.set_name, ci.name AS instrument_name
        FROM stock {SINGLE_INSTRUMENT}
    """, (cycle["id"],))
    instrument = stock["instrument_name"]
    return {
        "id": item["qr"], "label": item["label"], "set": stock["set_name"],
        "instrument": db.instrument_display_name(instrument) if instrument is not None else None,
    }


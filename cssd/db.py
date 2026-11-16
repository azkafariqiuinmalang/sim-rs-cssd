import atexit
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import click
from flask import current_app, g
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from .postgres import Postgres, connection_pool


MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
DEMO_ROLES = {
    "admin": ("admin", 1), "setting": ("petugas_cssd", 1),
    "steril": ("petugas_cssd", 1), "qc": ("petugas_cssd", 1),
    "gudang": ("petugas_cssd", 1), "ok": ("petugas_unit", 2),
    "ok2": ("petugas_unit", 3), "dekon": ("petugas_cssd", 1),
    "supervisor": ("supervisor", 1),
}

GRATI_CSSD_UNITS = (
    "R. IGD",
    "R. RANU",
    "R. BROMO",
    "R. KABER",
    "R. PERINATOLOGI",
    "R. ICU",
    "R. PINERE",
    "R. HEMODIALISA",
    "POLI BEDAH",
    "POLI ORTHOPEDI",
    "POLI GIGI",
    "POLI BEDAH SARAF",
    "POLI UROLOGI",
    "RUANG OPERASI",
    "FARMASI",
    "POLI OBGYN",
)

DEMO_SET_NAME = "Set Bedah Minor"
DEMO_INSTRUMENT_NAMES = {
    "Instrumen Demo A": "Klem Hemostat Mosquito Lurus",
    "Instrumen Demo B": "Pinset Anatomi",
    "Instrumen Demo C": "Gunting Metzenbaum Lengkung",
}


def instrument_display_name(name):
    return DEMO_INSTRUMENT_NAMES.get(name, name)


def connect(path):
    conn = sqlite3.connect(path, isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get():
    if "db" not in g:
        url = current_app.config["DATABASE_URL"]
        size = current_app.config["DATABASE_POOL_SIZE"]
        pool = None
        if url and size:
            extensions = current_app.extensions
            with extensions["cssd_pool_lock"]:
                pool = extensions.get("cssd_postgres_pool")
                if pool is None:
                    pool = connection_pool(url, size)
                    extensions["cssd_postgres_pool"] = pool
                    atexit.register(pool.close)
        g.db = Postgres(url, pool=pool) if url else connect(current_app.config["DATABASE"])
    return g.db


def close(_error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def migrate(conn, direction):
    if direction not in {"up", "down"}:
        raise ValueError(direction)
    target = 4 if direction == "up" else 0
    # SQLite rebuilds the users table while preserving referenced IDs.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with write_transaction(conn):
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in range(5):
                raise RuntimeError(f"Unsupported schema version: {version}")
            while version != target:
                step = version + 1 if direction == "up" else version
                sql = (MIGRATIONS / f"{step:03}_{direction}.sql").read_text(encoding="utf-8")
                statement = ""
                for line in sql.splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        conn.execute(statement)
                        statement = ""
                if statement.strip():
                    raise RuntimeError(f"Incomplete migration: {step:03}_{direction}")
                version += 1 if direction == "up" else -1
            if conn.execute("PRAGMA foreign_key_check").fetchone():
                raise RuntimeError("Migration would leave invalid foreign keys")
            conn.execute(f"PRAGMA user_version={target}")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


@contextmanager
def write_transaction(conn):
    if isinstance(conn, Postgres):
        with conn.transaction():
            conn.lock_writes()
            yield
        return

    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def insert(conn, query, params=()):
    return conn.execute(query + " RETURNING id", params).fetchone()["id"]


def add_grati_units(conn):
    conn.executemany(
        "INSERT INTO units(name) VALUES (?) ON CONFLICT(name) DO NOTHING",
        [(name,) for name in GRATI_CSSD_UNITS],
    )


def seed(conn, passwords, *, grati_inventory=False):
    with write_transaction(conn):
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            raise ValueError("Demo sudah memiliki akun. Gunakan database baru untuk seed ulang.")
        unit_names = ("CSSD", "OK Demo A", "OK Demo B")
        units = [insert(conn, "INSERT INTO units(name) VALUES (?)", (name,)) for name in unit_names]
        add_grati_units(conn)
        conn.executemany(
            "INSERT INTO users(username,name,password_hash,unit_id,role,can_release_qc) VALUES(?,?,?,?,?,?)",
            [(u, f"Petugas Demo {u}", generate_password_hash(passwords[u]), units[unit-1], role, int(u == "qc"))
             for u, (role, unit) in DEMO_ROLES.items()],
        )
        if grati_inventory:
            from .demo_inventory import seed_inventory

            seed_inventory(conn)
            return
        template = insert(conn, "INSERT INTO templates(name,version) VALUES(?,1)", (DEMO_SET_NAME,))
        for name, quantity in zip(DEMO_INSTRUMENT_NAMES.values(), (2, 1, 1), strict=True):
            instrument = insert(conn, "INSERT INTO instruments(name) VALUES (?)", (name,))
            conn.execute("INSERT INTO template_items VALUES(?,?,?)", (template, instrument, quantity))
        conn.executemany(
            "INSERT INTO containers(label,qr,template_id) VALUES (?,?,?)",
            [(f"C-{i:03}", secrets.token_urlsafe(18), template) for i in (1, 2)],
        )


def is_conflict(error):
    state = getattr(error, "sqlstate", None) or ""
    return isinstance(error, sqlite3.IntegrityError) or state.startswith("23")


def is_retryable(error):
    state = getattr(error, "sqlstate", None)
    sqlite_code = getattr(error, "sqlite_errorcode", 0)
    return (state in {"40001", "40P01", "55P03"}
            or sqlite_code & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED})


def apply_schema(conn):
    if isinstance(conn, Postgres):
        conn.migrate()
    else:
        migrate(conn, "up")


@click.command("migrate-db")
@with_appcontext
def migrate_db():
    apply_schema(get())
    click.echo("Skema CSSD siap digunakan.")


@click.command("seed-grati-units")
@with_appcontext
def seed_grati_units():
    conn = get()
    with write_transaction(conn):
        add_grati_units(conn)
    click.echo(f"{len(GRATI_CSSD_UNITS)} unit REKAP CSSD RSUD Grati tersedia.")


@click.command("init-demo")
@click.option("--grati-inventory", is_flag=True, help="Isi katalog dan inventaris simulasi RSUD Grati.")
@with_appcontext
def init_demo(grati_inventory):
    passwords = {username: secrets.token_urlsafe(15) for username in DEMO_ROLES}
    conn = get()
    apply_schema(conn)
    try:
        seed(conn, passwords, grati_inventory=grati_inventory)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("Akun sintetis dan sandi awal masing-masing:")
    for username, password in passwords.items():
        role, _ = DEMO_ROLES[username]
        permission = " + izin QC" if username == "qc" else ""
        click.echo(f"{username:12} {role}{permission} / {password}")

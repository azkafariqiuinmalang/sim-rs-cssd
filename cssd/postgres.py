from pathlib import Path
from urllib.parse import urlsplit


MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations" / "postgres"
WRITE_LOCK = 80324819804638102


def connection_options(url):
    try:
        from psycopg.conninfo import conninfo_to_dict
        from psycopg.rows import dict_row
    except ImportError:
        raise RuntimeError("Pasang requirements-supabase.txt untuk koneksi PostgreSQL.") from None
    host = urlsplit(url).hostname
    options = conninfo_to_dict(url)
    local = host in {"127.0.0.1", "::1", "localhost"}
    sslmode = options.get("sslmode", "prefer" if local else "require")
    if not local and sslmode not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("TLS required")
    return {"autocommit": True, "row_factory": dict_row, "connect_timeout": 5, "sslmode": sslmode}


def configure_connection(conn):
    conn.execute("SET search_path TO cssd_app, pg_catalog")
    conn.execute("SET TIME ZONE 'UTC'")
    conn.execute("SET lock_timeout TO '5s'")


def connection_pool(url, size):
    try:
        from psycopg_pool import ConnectionPool
    except ImportError:
        raise RuntimeError("Pasang requirements-supabase.txt untuk pool PostgreSQL.") from None
    return ConnectionPool(
        url, kwargs=connection_options(url), configure=configure_connection, open=False,
        min_size=0, max_size=size, max_waiting=size * 4, timeout=5,
    )


class Postgres:
    def __init__(self, url=None, *, pool=None):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Install requirements-supabase.txt to connect to PostgreSQL.") from exc

        self.pool = pool
        if pool is not None:
            from psycopg_pool import PoolTimeout, TooManyRequests
            from flask import abort

            pool.open()
            try:
                self.connection = pool.getconn()
            except (PoolTimeout, TooManyRequests):
                abort(503, "Koneksi database sedang sibuk. Coba lagi.")
            return
        try:
            self.connection = psycopg.connect(url, **connection_options(url))
            configure_connection(self.connection)
        except (psycopg.Error, ValueError):
            if hasattr(self, "connection"):
                self.connection.close()
            raise RuntimeError("Koneksi PostgreSQL gagal. Periksa URL, sandi, dan jaringan.") from None

    def execute(self, query, args=()):
        if not args:
            return self.connection.execute(query)
        return self.connection.execute(query.replace("?", "%s"), args)

    def executemany(self, query, args):
        with self.connection.cursor() as cursor:
            cursor.executemany(query.replace("?", "%s"), args)

    def transaction(self):
        return self.connection.transaction()

    def lock_writes(self):
        # Match the SQLite demo's single-writer behavior while keeping reads concurrent.
        self.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        self.execute("SELECT pg_advisory_xact_lock(?)", (WRITE_LOCK,))

    def close(self):
        if self.pool is not None:
            self.pool.putconn(self.connection)
        else:
            self.connection.close()

    def migrate(self):
        with self.transaction():
            self.lock_writes()
            for path in sorted(MIGRATIONS.glob("*_up.sql")):
                version = int(path.name.split("_")[0])
                marker = self.execute("SELECT to_regclass('cssd_app.schema_migrations') AS marker").fetchone()["marker"]
                if marker and self.execute(
                    "SELECT 1 FROM cssd_app.schema_migrations WHERE version=?", (version,)
                ).fetchone():
                    continue
                self.execute(path.read_text(encoding="utf-8"))
                self.execute("INSERT INTO cssd_app.schema_migrations(version) VALUES(?)", (version,))


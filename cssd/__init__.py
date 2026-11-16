from pathlib import Path
from threading import Lock

from flask import Flask

from . import db, supabase_auth
from .web import bp


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=str(Path(app.instance_path) / "demo.sqlite3"),
        DATABASE_URL=None,
        DATABASE_POOL_SIZE=4,
        SUPABASE_URL=None,
        SUPABASE_PUBLISHABLE_KEY=None,
        DEMO_GUIDE=False,
        SECRET_KEY=None,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    app.config.from_prefixed_env("CSSD")
    if config:
        app.config.update(config)
    if not app.secret_key:
        raise RuntimeError("Set CSSD_SECRET_KEY to a local random secret.")
    url = app.config["SUPABASE_URL"]
    key = app.config["SUPABASE_PUBLISHABLE_KEY"]
    if url or key:
        if not (url and key and app.config["DATABASE_URL"]):
            raise RuntimeError("Login Supabase memerlukan CSSD_SUPABASE_URL, CSSD_SUPABASE_PUBLISHABLE_KEY, dan CSSD_DATABASE_URL.")
        if not isinstance(key, str) or key.startswith("sb_secret_"):
            raise RuntimeError("Gunakan publishable key Supabase.")
        supabase_auth.validate_url(url)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.extensions["cssd_pool_lock"] = Lock()
    app.teardown_appcontext(db.close)
    app.cli.add_command(db.init_demo)
    app.cli.add_command(db.migrate_db)
    app.cli.add_command(db.seed_grati_units)
    app.register_blueprint(bp)
    return app


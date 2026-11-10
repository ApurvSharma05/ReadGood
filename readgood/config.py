"""Application configuration, read from environment variables."""
import logging
import os
import secrets
from datetime import timedelta
from pathlib import Path


def _flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


ON_VERCEL = bool(os.getenv("VERCEL"))


def _database_uri():
    """Use DATABASE_URL (or Vercel's POSTGRES_URL) when set, else local SQLite."""
    uri = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
    if not uri:
        if ON_VERCEL:
            # Vercel's disk is read-only except /tmp, and /tmp is wiped between
            # cold starts: fine for a smoke test, not for real accounts.
            logging.getLogger(__name__).warning(
                "No DATABASE_URL set on Vercel: using a temporary SQLite file. "
                "Accounts will be lost. Connect a Postgres database."
            )
            return "sqlite:////tmp/readgood.db"
        return "sqlite:///books.db"
    for prefix in ("postgres://", "postgresql://"):
        if uri.startswith(prefix):
            return "postgresql+psycopg://" + uri[len(prefix):]
    return uri


def _secret_key(app, production):
    key = os.getenv("SECRET_KEY", "").strip()
    if key:
        return key
    if production:
        raise RuntimeError(
            "SECRET_KEY must be set when APP_ENV=production. "
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    # Development: keep a generated key in the instance folder so sessions
    # survive restarts without anyone having to hardcode a key.
    key_file = Path(app.instance_path) / "secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    return key


def configure(app, test_config=None):
    # Vercel deployments count as production unless APP_ENV says otherwise.
    default_env = "production" if ON_VERCEL else "development"
    production = os.getenv("APP_ENV", default_env).strip().lower() == "production"

    app.config.update(
        PRODUCTION=production,
        SQLALCHEMY_DATABASE_URI=_database_uri(),
        # Small pool with recycling: serverless functions are short-lived and
        # hosted Postgres closes idle connections.
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 280},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_flag("SESSION_COOKIE_SECURE", production),
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        TRUST_PROXY=_flag("TRUST_PROXY", production),
        WTF_CSRF_TIME_LIMIT=None,
        CACHE_TYPE=os.getenv("CACHE_TYPE", "SimpleCache"),
        CACHE_DEFAULT_TIMEOUT=3600,
        CACHE_THRESHOLD=2000,
        RATELIMIT_STORAGE_URI=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
        RATELIMIT_HEADERS_ENABLED=True,
        MAX_CONTENT_LENGTH=256 * 1024,
    )

    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _secret_key(app, production)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Generator
from config import settings
import atexit

try:
    from sshtunnel import SSHTunnelForwarder  # type: ignore
except Exception:
    SSHTunnelForwarder = None  # type: ignore

# Configure SQLAlchemy engine
is_sqlite = settings.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

_tunnel = None
_connection_url = settings.DATABASE_URL

if not is_sqlite and getattr(settings, "USE_SSH_TUNNEL", False):
    if SSHTunnelForwarder is None:
        raise RuntimeError("sshtunnel package not installed; please add 'sshtunnel' to requirements and install it.")
    required = [
        settings.SSH_HOST,
        settings.SSH_USERNAME,
        settings.SSH_PASSWORD,
        settings.DB_NAME,
        settings.DB_USERNAME,
        settings.DB_PASSWORD,
    ]
    if not all(required):
        raise RuntimeError("Missing SSH/DB credentials. Set SSH_HOST, SSH_USERNAME, SSH_PASSWORD, DB_NAME, DB_USERNAME, DB_PASSWORD in your environment or .env")

    ssh_host = settings.SSH_HOST
    ssh_port = getattr(settings, "SSH_PORT", 22)
    remote_host = getattr(settings, "DB_HOST", "127.0.0.1")
    remote_port = getattr(settings, "DB_PORT", 5432)

    _tunnel = SSHTunnelForwarder(
        (ssh_host, ssh_port),
        ssh_username=settings.SSH_USERNAME,
        ssh_password=settings.SSH_PASSWORD,
        remote_bind_address=(remote_host, remote_port),
        local_bind_address=("127.0.0.1", 0),  # assign a random free local port
    )
    _tunnel.start()

    _connection_url = f"postgresql+psycopg2://{settings.DB_USERNAME}:{settings.DB_PASSWORD}@127.0.0.1:{_tunnel.local_bind_port}/{settings.DB_NAME}"

    def _stop_tunnel():
        try:
            if _tunnel:
                _tunnel.stop()
        except Exception:
            pass
    atexit.register(_stop_tunnel)

engine = create_engine(
    _connection_url,
    echo=False,
    future=True,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency for FastAPI
def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- lightweight, runtime-safe schema upgrade helpers ---
# We avoid full migrations here and only add missing columns if needed.
from sqlalchemy import inspect, text

def ensure_schema_upgrades() -> None:
    try:
        inspector = inspect(engine)
        # users table: add full_name if missing
        cols = [c['name'] for c in inspector.get_columns('users')]
        if 'full_name' not in cols:
            # SQLite and Postgres both accept VARCHAR syntax here; use TEXT for sqlite for compatibility
            with engine.begin() as conn:
                if is_sqlite:
                    conn.execute(text("ALTER TABLE users ADD COLUMN full_name TEXT"))
                else:
                    conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR(255)"))
        # executions table: add submitted_by_user_id if missing
        exec_cols = [c['name'] for c in inspector.get_columns('executions')]
        if 'submitted_by_user_id' not in exec_cols:
            with engine.begin() as conn:
                # INTEGER works for both sqlite and postgres
                conn.execute(text("ALTER TABLE executions ADD COLUMN submitted_by_user_id INTEGER"))
    except Exception:
        # Silently ignore to avoid crashing startup; app will still run
        pass
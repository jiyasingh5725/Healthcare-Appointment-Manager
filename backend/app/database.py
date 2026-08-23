import logging
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings, BASE_DIR

logger = logging.getLogger(__name__)

# SQLAlchemy declarative base for all ORM models
Base = declarative_base()


def _init_engine():
    """
    Initialize database engine with automatic SQLite fallback if MySQL is unreachable.
    """
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite"):
        return create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            echo=settings.DEBUG,
        )

    try:
        eng = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=settings.DEBUG,
        )
        with eng.connect() as conn:
            pass
        return eng
    except Exception as e:
        logger.warning(
            f"MySQL connection to {db_url} failed ({e}). Falling back to local SQLite database."
        )
        db_file = (BASE_DIR.parent / "healthcare_manager.db").resolve()
        sqlite_url = f"sqlite:///{db_file.as_posix()}"
        return create_engine(
            sqlite_url,
            connect_args={"check_same_thread": False},
            echo=settings.DEBUG,
        )


engine = _init_engine()

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Ensure all model tables are created and migrate any missing columns."""
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    try:
        from sqlalchemy import inspect, text
        with engine.connect() as conn:
            inspector = inspect(conn)
            if "notifications" in inspector.get_table_names():
                cols = [c["name"] for c in inspector.get_columns("notifications")]
                if "notification_type" not in cols:
                    conn.execute(text("ALTER TABLE notifications ADD COLUMN notification_type VARCHAR(50) DEFAULT 'BOOKING_CONFIRMATION'"))
                if "channel" not in cols:
                    conn.execute(text("ALTER TABLE notifications ADD COLUMN channel VARCHAR(20) DEFAULT 'EMAIL'"))
                if "status" not in cols:
                    conn.execute(text("ALTER TABLE notifications ADD COLUMN status VARCHAR(20) DEFAULT 'PENDING'"))
                if "retry_count" not in cols:
                    conn.execute(text("ALTER TABLE notifications ADD COLUMN retry_count INTEGER DEFAULT 0"))
                if "error_message" not in cols:
                    conn.execute(text("ALTER TABLE notifications ADD COLUMN error_message TEXT"))
                if "scheduled_at" not in cols:
                    conn.execute(text("ALTER TABLE notifications ADD COLUMN scheduled_at TIMESTAMP"))
                if "sent_at" not in cols:
                    conn.execute(text("ALTER TABLE notifications ADD COLUMN sent_at TIMESTAMP"))
                conn.commit()
    except Exception as e:
        logger.warning(f"[DB:Migration] Minor schema sync notice: {e}")


# Auto-initialize tables
init_db()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency helper that yields database sessions and guarantees cleanup.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

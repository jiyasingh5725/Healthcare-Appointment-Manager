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
    """Ensure all model tables are created, migrate columns, and seed initial demo accounts."""
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

    # Seed default Admin, Doctor, and Demo Patient accounts
    try:
        from datetime import time as dt_time
        from app.utils.security import hash_password
        from app.models.user import User, UserRole
        from app.models.doctor import Doctor
        from app.models.doctor_schedule import DoctorWorkingHours

        seed_db = SessionLocal()
        try:
            # 1. Seed Admin
            admin_user = seed_db.query(User).filter(User.email == "admin@hospital.org").first()
            if not admin_user:
                admin_user = User(
                    name="System Administrator",
                    email="admin@hospital.org",
                    password_hash=hash_password("AdminPass123!"),
                    role=UserRole.ADMIN,
                    phone="1234567890",
                    is_active=True,
                )
                seed_db.add(admin_user)
                seed_db.commit()
                logger.info("[DB:Seed] Seeded default Admin: admin@hospital.org")

            # 2. Seed Doctor
            doc_user = seed_db.query(User).filter(User.email == "doctor@hospital.org").first()
            if not doc_user:
                doc_user = User(
                    name="Dr. Gregory House",
                    email="doctor@hospital.org",
                    password_hash=hash_password("DoctorPass123!"),
                    role=UserRole.DOCTOR,
                    phone="1234567891",
                    is_active=True,
                )
                seed_db.add(doc_user)
                seed_db.commit()
                seed_db.refresh(doc_user)

                doc_profile = Doctor(
                    user_id=doc_user.id,
                    specialization="Cardiology",
                    qualification="MD, FACC",
                    experience=12,
                    slot_duration=30,
                    is_active=True,
                )
                seed_db.add(doc_profile)
                seed_db.commit()
                seed_db.refresh(doc_profile)

                # Mon to Fri working hours (0-4) 09:00 - 17:00
                for day in range(5):
                    wh = DoctorWorkingHours(
                        doctor_id=doc_profile.id,
                        day_of_week=day,
                        start_time=dt_time(9, 0),
                        end_time=dt_time(17, 0),
                    )
                    seed_db.add(wh)
                seed_db.commit()
                logger.info("[DB:Seed] Seeded default Doctor: doctor@hospital.org")

            # 3. Seed Demo Patient
            patient_user = seed_db.query(User).filter(User.email == "patient@example.com").first()
            if not patient_user:
                patient_user = User(
                    name="Demo Patient",
                    email="patient@example.com",
                    password_hash=hash_password("Password123!"),
                    role=UserRole.PATIENT,
                    phone="1234567892",
                    is_active=True,
                )
                seed_db.add(patient_user)
                seed_db.commit()
                logger.info("[DB:Seed] Seeded default Patient: patient@example.com")

        except Exception as err:
            seed_db.rollback()
            logger.warning(f"[DB:Seed] Seed execution notice: {err}")
        finally:
            seed_db.close()
    except Exception as e:
        logger.warning(f"[DB:Seed] Could not complete initial seeding: {e}")


def get_db() -> Generator[Session, None, None]:
    """
    Dependency helper that yields database sessions and guarantees cleanup.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Auto-initialize tables and seed initial demo accounts
init_db()


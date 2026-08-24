import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory paths
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# Load .env file if it exists
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
else:
    load_dotenv(override=True)


class Settings:
    """Application Settings configuration class."""

    APP_NAME: str = os.getenv("APP_NAME", "Healthcare Appointment & Follow-up Manager")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "t")
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", 8000))

    # CORS Origins
    _raw_cors = os.getenv("CORS_ORIGINS", "*")
    CORS_ORIGINS: list[str] = [
        origin.strip() for origin in _raw_cors.split(",") if origin.strip()
    ] if _raw_cors != "*" else ["*"]

    # Database Configuration
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'healthcare_manager.db').as_posix()}"
    )

    # JWT Settings (Placeholder for future phases)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default_secret_key_for_development")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

    # AI / LLM Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "gemini-flash-latest")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")

    # Redis & Celery Background Tasks Configuration (Phase 15)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))

    # Email Notification System Configuration (Phase 16)
    EMAIL_PROVIDER: str = os.getenv("EMAIL_PROVIDER", "mock").lower()  # sendgrid, mailgun, smtp, mock
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    MAILGUN_API_KEY: str = os.getenv("MAILGUN_API_KEY", "")
    MAILGUN_DOMAIN: str = os.getenv("MAILGUN_DOMAIN", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "noreply@caresync-health.org")
    EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME", "CareSync Health Notifications")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "localhost")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_TLS: bool = os.getenv("SMTP_TLS", "True").lower() in ("true", "1", "t")

    # Google Calendar & OAuth 2.0 Configuration (Phase 18)
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/calendar/callback")


settings = Settings()




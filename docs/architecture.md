# Healthcare Appointment & Follow-up Manager - Architecture

## System Overview
- **Frontend**: Vanilla HTML5, CSS3, Tailwind CSS, JavaScript (Fetch API)
- **Backend**: Python FastAPI, SQLAlchemy, Alembic
- **Database**: MySQL
- **Authentication**: JWT, bcrypt/Argon2 (Future Phase)
- **Background Tasks**: Redis, Celery (Future Phase)
- **AI Integrations**: LLM API (Future Phase)
- **Notifications**: SendGrid/Mailgun (Future Phase)
- **Calendar**: Google Calendar API + OAuth 2.0 (Future Phase)

## API Endpoints (Phase 1)
- `GET /api/health` - Health check status

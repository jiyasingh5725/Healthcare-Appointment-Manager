# CareSync: Healthcare Appointment & Clinical Management Platform

CareSync is a secure, resilient healthcare appointment and follow-up management platform engineered with FastAPI, SQLAlchemy, Redis, Celery, Google Gemini AI, and Google Calendar integration. It features dedicated portals for patients, attending physicians, and hospital administrators.

---

## 🌟 Key Features

### 👤 Patient Portal
- **Smart Appointment Booking**: Dynamic slot discovery based on weekly working hours, doctor leaves, and existing bookings.
- **Atomic Slot Holds**: 10-minute temporary slot reservation to prevent race conditions during booking.
- **Rescheduling & Cancellations**: Atomic appointment updates, freed slot releases, and automatic history preservation.
- **Medication Reminders**: Track active prescribed medications with automated background reminder notifications.
- **Google Calendar Sync**: Real-time two-way synchronization of confirmed appointments to Google Calendar via OAuth 2.0.

### 🩺 Doctor Clinical Workspace
- **Daily Agenda & Schedule**: Filter today's consultations, upcoming queues, and completed patient cases.
- **AI Clinical Summaries**: Instant structured pre-consultation symptom summaries powered by Google Gemini AI with heuristic fallbacks.
- **Consultations & Prescriptions**: Record diagnoses, clinical notes, and structured medication courses (dosage, frequency, instructions).

### 🛡️ Admin Operations Panel
- **Medical Staff Directory**: Onboard physicians, configure consultation slot durations, and manage account statuses.
- **Shift & Leave Management**: Configure weekly shift hours and schedule doctor leaves with automatic conflict resolution.
- **System Metrics & Delivery Monitor**: Real-time tracking of users, appointments, leave conflicts, and email notification health.

---

## 🏗️ System Architecture

```
CareSync/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application entry point
│   │   ├── config.py            # Environment configurations
│   │   ├── database.py          # SQLAlchemy engine & session lifecycle
│   │   ├── models/              # Relational database models
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── routes/              # Modular REST API endpoints
│   │   ├── services/            # Core business logic & ACID transactions
│   │   ├── tasks/               # Celery background workers & schedules
│   │   └── utils/               # Security, hashing, & OAuth dependencies
│   ├── alembic/                 # Database migrations
│   ├── requirements.txt         # Python dependencies
│   └── .env.example             # Environment template
├── frontend/
│   ├── index.html               # Landing page
│   ├── login.html               # Authentication & session gate
│   ├── register.html            # Patient registration
│   ├── patient/                 # Patient portal (Dashboard, Booking, Profile)
│   ├── doctor/                  # Doctor portal (Agenda, Case Review, Notes)
│   ├── admin/                   # Admin portal (Staff Directory, Leaves, Monitor)
│   ├── css/styles.css           # Design system, glassmorphism, & skeletons
│   └── js/                      # API client, Auth state, & UI helpers
├── docs/                        # Complete technical documentation
│   ├── system-design.md         # Architecture, ACID transactions & concurrency
│   ├── api-documentation.md     # OpenAPI REST endpoints & schemas
│   ├── database-schema.md       # Relational tables, keys, & indexes
│   ├── llm-prompts.md           # Gemini AI prompts & clinical safety
│   └── google-calendar-setup.md # Google OAuth 2.0 & Calendar sync guide
└── tests/                       # Automated end-to-end test suites
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python**: 3.10+
- **Redis Server**: 6.0+ (Local executable, Memurai for Windows, or Docker)

### 2. Backend Installation & Setup
```bash
# Clone repository
git clone https://github.com/your-org/healthcare-appointment-manager.git
cd Healthcare-Appointment-Manager

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Configure environment
cp backend/.env.example backend/.env
```

### 3. Start the FastAPI Server
```bash
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```
- **API Health Check**: `http://127.0.0.1:8000/api/health`
- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`

### 4. Start Redis & Celery Background Workers
In separate terminal tabs:

**A. Start Redis:**
```bash
# Docker:
docker run -d -p 6379:6379 --name redis-healthcare redis:alpine
# Or Windows Redis:
redis-server.exe
```

**B. Start Celery Worker (Windows compatible):**
```bash
cd backend
celery -A app.tasks.celery_app worker -l info -P solo
```

**C. Start Celery Beat Scheduler (for periodic reminder checks & expired hold cleanup):**
```bash
cd backend
celery -A app.tasks.celery_app beat -l info
```

### 5. Launch the Frontend
Open `frontend/index.html` directly in your browser, or serve using any static web server:
```bash
# Using Python HTTP server
python -m http.server 3000 --directory frontend
```
Navigate to `http://127.0.0.1:3000`.

---

## 🧪 Running Automated Test Suites

CareSync includes comprehensive automated test suites covering all core workflows:

```bash
# Phase 16: Email & Multichannel Notification Delivery
python tests/test_phase16_email_notifications.py

# Phase 17: Background Reminders & Celery Beat Automation
python tests/test_phase17_background_reminders.py

# Phase 18: Google Calendar OAuth 2.0 & Synchronization
python tests/test_phase18_google_calendar.py

# Phase 19: Complete Reschedule & Cancellation Synchronization
python tests/test_phase19_appointment_synchronization.py
```

---

## 📚 Technical Documentation

- [System Design Document](file:///docs/system-design.md): Deep-dive into double-booking prevention, locking, ACID transactions, doctor leave resolution, and failure resilience.
- [REST API Specification](file:///docs/api-documentation.md): Comprehensive endpoint specifications with parameters, request payloads, and response models.
- [Database Schema](file:///docs/database-schema.md): Complete data dictionary covering all tables, foreign keys, and indexes.
- [LLM Prompts & AI Clinical Integration](file:///docs/llm-prompts.md): Gemini AI prompt templates, JSON schema validation, and fallback heuristics.
- [Google Calendar Setup Guide](file:///docs/google-calendar-setup.md): Step-by-step setup for Google Cloud Console OAuth 2.0 credentials and background sync.

---

## 📄 License
CareSync is distributed under the MIT License.
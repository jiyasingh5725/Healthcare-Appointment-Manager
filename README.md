# CareSync: Healthcare Appointment & Clinical Management Platform

[![Live Demo](https://img.shields.io/badge/Live_Demo-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://caresync-healthcare.onrender.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![Google Gemini AI](https://img.shields.io/badge/Google_Gemini_AI-8E75B2?style=for-the-badge&logo=google-gemini&logoColor=white)](https://aistudio.google.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

> **Live Production Website**: 🌐 **[https://caresync-healthcare.onrender.com](https://caresync-healthcare.onrender.com)**  
> **Interactive Swagger API Documentation**: 📖 **[https://caresync-healthcare.onrender.com/docs](https://caresync-healthcare.onrender.com/docs)**

---

## 📸 Platform UI Showcase

### 🌐 1. Landing Page & Portal Gateway
| CareSync Hero Landing Page | Role-Based Portal Gateway |
| :---: | :---: |
| ![CareSync Landing Page](docs/screenshots/sc2.png) | ![Portal Selection](docs/screenshots/sc1.png) |

---

### 👤 2. Patient Experience & Smart Consultation Flow

#### A. Patient Dashboard & Real-Time Notification System
| Patient Overview & Upcoming Visits | Real-Time Clinical Notifications |
| :---: | :---: |
| ![Patient Dashboard](docs/screenshots/p1.png) | ![Notifications Dropdown](docs/screenshots/p19.png) |

| Health Metrics & Recent Records | Google Calendar Sync & Medication Alerts |
| :---: | :---: |
| ![Patient Stats](docs/screenshots/p2.png) | ![Calendar & Medications](docs/screenshots/p3.png) |

#### B. Specialist Search & Dynamic Slot Selection
| Find Specialists by Department | Interactive Time Slot Picker Modal |
| :---: | :---: |
| ![Find Specialists](docs/screenshots/p6.png) | ![Slot Selection](docs/screenshots/p10.png) |

| Filter by Medical Specialization | Time Slot Selection with Hold System |
| :---: | :---: |
| ![Specialization Filter](docs/screenshots/p9.png) | ![Slot Selected](docs/screenshots/p11.png) |

#### C. Intelligent Booking & Clinical Intake
| Select Physician & Booking Date | Symptom Intake & Summary Confirmation |
| :---: | :---: |
| ![Booking Form](docs/screenshots/p12.png) | ![Symptom Intake](docs/screenshots/p13.png) |

#### D. Consultation History, Diagnosis & AI-Generated Recovery Plan
| Scheduled Consultations Record Table | Completed Consultation Details |
| :---: | :---: |
| ![My Appointments](docs/screenshots/p14.png) | ![Consultation Record](docs/screenshots/p15.png) |

| Physician Diagnosis & Prescriptions | AI-Generated Patient Recovery Plan |
| :---: | :---: |
| ![Diagnosis & Prescription](docs/screenshots/p16.png) | ![AI Care Summary](docs/screenshots/p17.png) |

| Patient Profile & Account Security |
| :---: |
| ![Patient Profile](docs/screenshots/p20.png) |

---

### 🩺 3. Attending Doctor Clinical Workspace
| Doctor Agenda & Daily Patient Queue | AI Clinical Pre-Visit Summary & Decision Support |
| :---: | :---: |
| ![Doctor Dashboard](docs/screenshots/doc_dashboard.png) | ![AI Decision Support](docs/screenshots/doc_ai_summary.png) |

---

### 🛡️ 4. Central Hospital Administration Panel
| Hospital Metrics & Operations Overview | Medical Staff Directory & Account Control |
| :---: | :---: |
| ![Admin Dashboard](docs/screenshots/admin_dashboard.png) | ![Staff Directory](docs/screenshots/admin_staff.png) |

| Weekly Consultation Shift Schedule | Doctor Leave & Automated Conflict Management |
| :---: | :---: |
| ![Weekly Working Hours](docs/screenshots/admin_schedule.png) | ![Doctor Leaves](docs/screenshots/admin_leaves.png) |

| Real-Time SMTP Email & Notification Monitor |
| :---: |
| ![SMTP Notification Logs](docs/screenshots/admin_notifications.png) |

---

## 🔑 Quick 1-Click Demo Accounts

The platform comes pre-seeded with instant demo credentials for immediate evaluation:

| Role | Email | Password | Key Capabilities |
| :--- | :--- | :--- | :--- |
| **🛡️ Hospital Admin** | `admin@hospital.org` | `AdminPass123!` | Onboard physicians, configure shift schedules, manage doctor leaves, and view system metrics. |
| **🩺 Attending Doctor** | `doctor@hospital.org` | `DoctorPass123!` | Review consultation queues, view AI clinical triage summaries, and prescribe medication courses. |
| **👤 Demo Patient** | `patient@example.com` | `Password123!` | Real-time smart slot booking, atomic 10-min slot holds, Google Calendar sync, and email alerts. |

---

## 🌟 Key Features

### 👤 Patient Portal
- **Smart Appointment Booking**: Dynamic slot discovery calculated from weekly shift hours, doctor leaves, and existing bookings.
- **Atomic Slot Holds**: 10-minute temporary slot reservation to eliminate race conditions and double-booking.
- **Rescheduling & Cancellations**: Immediate slot release, audit trail logging, and calendar sync updates.
- **Medication Reminders**: Track prescribed medications with dosage, frequency, and background reminder alerts.
- **Google Calendar Sync**: Real-time two-way synchronization of confirmed appointments to Google Calendar via OAuth 2.0.

### 🩺 Doctor Clinical Workspace
- **Daily Agenda & Schedule**: Filter today's consultations, upcoming queues, and completed patient cases.
- **AI Clinical Summaries**: Instant structured pre-consultation symptom summaries powered by **Google Gemini AI** with heuristic fallbacks.
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
│   │   ├── main.py              # FastAPI application entry point & static mounting
│   │   ├── config.py            # Environment configurations
│   │   ├── database.py          # SQLAlchemy engine, session lifecycle & auto-seeding
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
│   ├── login.html               # Authentication & 1-click role switcher
│   ├── register.html            # Patient registration
│   ├── patient/                 # Patient portal (Dashboard, Booking, Profile)
│   ├── doctor/                  # Doctor portal (Agenda, Case Review, Notes)
│   ├── admin/                   # Admin portal (Staff Directory, Leaves, Monitor)
│   ├── css/styles.css           # Design system, glassmorphism, & skeletons
│   └── js/                      # API client, Auth state, & UI helpers
├── docs/                        # Complete technical documentation
│   ├── screenshots/             # High-resolution platform UI preview images
│   ├── system-design.md         # Architecture, ACID transactions & concurrency
│   ├── api-documentation.md     # OpenAPI REST endpoints & schemas
│   ├── database-schema.md       # Relational tables, keys, & indexes
│   ├── llm-prompts.md           # Gemini AI prompts & clinical safety
│   └── google-calendar-setup.md # Google OAuth 2.0 & Calendar sync guide
└── tests/                       # Automated end-to-end test suites
```

---

## 🚀 Local Development Setup

### 1. Prerequisites
- **Python**: 3.10+
- **Redis Server** *(Optional for Celery workers)*: 6.0+

### 2. Backend Installation & Startup
```bash
# 1. Clone repository
git clone https://github.com/jiyasingh5725/Healthcare-Appointment-Manager.git
cd Healthcare-Appointment-Manager

# 2. Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 3. Install dependencies
pip install -r backend/requirements.txt

# 4. Configure environment
cp backend/.env.example backend/.env

# 5. Start unified FastAPI & Frontend Server
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

- **Website**: `http://127.0.0.1:8000`
- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`
- **Health Check**: `http://127.0.0.1:8000/api/health`

---

## 🧪 Running Automated Test Suites

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

- [System Design Document](docs/system-design.md): Concurrency control, double-booking prevention, locking, ACID transactions, and doctor leave resolution.
- [REST API Specification](docs/api-documentation.md): Comprehensive endpoint specifications with parameters, request payloads, and response models.
- [Database Schema](docs/database-schema.md): Complete data dictionary covering all relational tables, foreign keys, and indexes.
- [LLM Prompts & AI Clinical Integration](docs/llm-prompts.md): Gemini AI prompt templates, JSON schema validation, and fallback heuristics.
- [Google Calendar Setup Guide](docs/google-calendar-setup.md): Step-by-step setup for Google Cloud Console OAuth 2.0 credentials and background sync.
- [Production Deployment Guide](docs/deployment.md): Detailed deployment instructions for cloud servers and containerized setups.

---

## 📄 License
CareSync is distributed under the MIT License.
# REST API Documentation: CareSync Healthcare Platform

CareSync exposes an interactive OpenAPI (Swagger) interface at `http://127.0.0.1:8000/docs`. All JSON requests and responses follow standard REST conventions and authenticate via JWT Bearer tokens in the `Authorization: Bearer <token>` header.

---

## 1. Authentication & User Management (`/api/auth`)

### `POST /api/auth/register`
- **Role Required**: Public
- **Description**: Registers a new patient account.
- **Request Body**:
```json
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "password": "Password123!",
  "phone": "+1-555-0199"
}
```
- **Response `201 Created`**: User profile without password hash.

### `POST /api/auth/login`
- **Role Required**: Public
- **Description**: Authenticates user credentials and issues a JWT access token.
- **Request Body**:
```json
{
  "email": "jane@example.com",
  "password": "Password123!"
}
```
- **Response `200 OK`**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "role": "PATIENT",
  "name": "Jane Doe",
  "email": "jane@example.com"
}
```

### `GET /api/auth/me`
- **Role Required**: Authenticated (`PATIENT`, `DOCTOR`, `ADMIN`)
- **Description**: Returns authenticated user session profile.

---

## 2. Doctors & Public Directory (`/api/doctors`)

### `GET /api/doctors`
- **Role Required**: Public
- **Query Parameters**:
  - `search` *(string, optional)*: Filter by doctor name or specialization.
  - `specialization` *(string, optional)*: Filter by exact medical specialty.
  - `active_only` *(bool, default: `true`)*: Return only active physicians.
- **Response `200 OK`**: List of doctor objects including ID, name, email, specialization, qualification, experience, and slot duration.

### `GET /api/doctors/{doctor_id}`
- **Role Required**: Public
- **Description**: Retrieves full profile of a specific physician.

---

## 3. Patient Portal & Medication Reminders (`/api/patient`)

### `GET /api/patient/dashboard`
- **Role Required**: `PATIENT`
- **Description**: Retrieves aggregated patient dashboard summary (next appointment, recent visits, active prescriptions count, unread notifications).

### `GET /api/patient/medications`
- **Role Required**: `PATIENT`
- **Description**: Lists all prescribed medications with active schedules and dosage timings.

### `PATCH /api/patient/medications/{prescription_item_id}/reminder`
- **Role Required**: `PATIENT`
- **Description**: Enables or disables automated background reminders for a specific medication.

---

## 4. Doctor Clinical Portal (`/api/doctor`)

### `GET /api/doctor/dashboard`
- **Role Required**: `DOCTOR`
- **Description**: Retrieves clinical stats (today's appointments, upcoming queue, completed consultations).

### `GET /api/doctor/appointments/today`
- **Role Required**: `DOCTOR`
- **Description**: Lists all patient consultations scheduled for the current calendar date.

---

## 5. Appointment Management & Synchronization (`/api/appointments`)

### `GET /api/appointments/slots`
- **Role Required**: Public / Authenticated
- **Query Parameters**: `doctor_id` *(int)*, `date` *(YYYY-MM-DD)*
- **Description**: Calculates dynamically available booking slots based on weekly working hours, active doctor leaves, existing bookings, and active temporary holds.

### `POST /api/appointments/hold`
- **Role Required**: `PATIENT`
- **Description**: Places an atomic 10-minute temporary reservation on a selected time slot.

### `POST /api/appointments`
- **Role Required**: `PATIENT`
- **Description**: Creates and confirms an appointment, verifying slot validity and double-booking constraints.
- **Request Body**:
```json
{
  "doctor_id": 1,
  "appointment_date": "2026-09-15",
  "start_time": "10:00:00",
  "symptoms": "Mild fever and sore throat for 3 days"
}
```

### `POST /api/appointments/{appointment_id}/reschedule`
- **Role Required**: `PATIENT` (Owner) or `DOCTOR` / `ADMIN`
- **Description**: Reschedules date and time with atomic conflict checks, updating Google Calendar and dispatching notifications.
- **Request Body**:
```json
{
  "new_date": "2026-09-18",
  "new_start_time": "14:00:00"
}
```

### `POST /api/appointments/{appointment_id}/cancel`
- **Role Required**: `PATIENT` (Owner), `DOCTOR`, or `ADMIN`
- **Description**: Releases booked slot while preserving audit history, cleans up Google Calendar, and logs reason.

---

## 6. Doctor Schedules & Leave Conflict Engine (`/api/admin/doctors/{doctor_id}`)

### `GET /api/admin/doctors/{doctor_id}/working-hours`
- **Role Required**: `ADMIN`
- **Description**: Returns weekly schedule (Monday through Sunday) for the doctor.

### `PUT /api/admin/doctors/{doctor_id}/working-hours`
- **Role Required**: `ADMIN`
- **Description**: Configures working shifts and slot durations across the 7-day week.

### `POST /api/admin/doctors/{doctor_id}/leaves`
- **Role Required**: `ADMIN`
- **Description**: Provisions a doctor leave date, detects conflicting appointments, auto-cancels with audit reasons, and queues patient notifications.

---

## 7. AI Clinical Summaries (`/api/appointments/{appointment_id}/ai-summary`)

### `POST /api/appointments/{appointment_id}/ai-summary`
- **Role Required**: `DOCTOR` / `ADMIN`
- **Description**: Triggers Gemini AI clinical symptom parsing, structured keypoint extraction, and risk assessment with deterministic heuristic fallbacks.

### `GET /api/appointments/{appointment_id}/ai-summary`
- **Role Required**: `DOCTOR` / `ADMIN`
- **Description**: Retrieves cached AI clinical summary for the consultation.

---

## 8. Prescriptions & Clinical Notes (`/api/appointments/{appointment_id}/prescription`)

### `POST /api/appointments/{appointment_id}/prescription`
- **Role Required**: `DOCTOR`
- **Description**: Records clinical diagnosis, physician notes, and structured medication items (name, dosage, frequency, duration, instructions).

---

## 9. Google Calendar & OAuth 2.0 (`/api/calendar`)

### `GET /api/calendar/connect`
- **Role Required**: `PATIENT`
- **Description**: Generates Google OAuth 2.0 consent URL with signed anti-tamper state.

### `GET /api/calendar/callback`
- **Role Required**: Public (OAuth redirect)
- **Description**: Exchanges authorization code for refresh tokens and stores encrypted credentials.

### `GET /api/calendar/status`
- **Role Required**: `PATIENT`
- **Description**: Returns Google Calendar connection health, synced calendar ID, and email.

---

## 10. Admin Operational Metrics (`/api/admin`)

### `GET /api/admin/metrics`
- **Role Required**: `ADMIN`
- **Description**: Returns real-time aggregate statistics for registered users, active physicians, appointment totals, leave conflict counts, and notification delivery health.

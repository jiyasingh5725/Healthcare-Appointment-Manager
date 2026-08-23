# Database Schema Documentation: CareSync Healthcare Platform

CareSync uses a relational database schema managed through SQLAlchemy ORM and Alembic migrations.

```
+---------------------------------------------------------------------------------+
|                                 CareSync Data Model                             |
|                                                                                 |
|   +---------------+ 1        1 +----------------+ 1        * +--------------+   |
|   |     users     +------------+    doctors     +------------+ working_hours|   |
|   +-------+-------+            +-------+--------+            +--------------+   |
|           | 1                          | 1                         *            |
|           |                            | +-----------------------+ doctor_leaves|
|           |                            |                                        |
|           | 1                          | 1                                      |
|           | *                          | *                                      |
|   +-------+-------+            +-------+--------+                               |
|   | notifications |            |  appointments  |                               |
|   +---------------+            +-------+--------+                               |
|                                        | 1                                      |
|                                        +-------------------+                    |
|                                        | 1                 | 1                  |
|                                        v                   v                    |
|                                +---------------+   +----------------+           |
|                                | prescriptions |   | calendar_events|           |
|                                +-------+-------+   +----------------+           |
|                                        | 1                                      |
|                                        v *                                      |
|                                +-------------------+                            |
|                                |prescription_items |                            |
|                                +-------------------+                            |
+---------------------------------------------------------------------------------+
```

---

## 1. Table: `users`
Stores all platform accounts (Patients, Doctors, Administrators) with RBAC authorization and secure bcrypt credentials.

| Column | Type | Nullable | Default / Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | Primary Key, Auto Increment | Unique user ID |
| `name` | `VARCHAR(120)` | No | | Full name |
| `email` | `VARCHAR(255)` | No | Unique, Indexed | Login email |
| `password_hash` | `VARCHAR(255)` | No | | Bcrypt password hash |
| `role` | `ENUM` | No | `'PATIENT'` (`PATIENT`, `DOCTOR`, `ADMIN`) | Account role |
| `phone` | `VARCHAR(30)` | Yes | | Contact phone number |
| `is_active` | `BOOLEAN` | No | `TRUE` | Account active flag |
| `created_at` | `DATETIME` | No | `UTC_NOW()` | Account creation timestamp |
| `updated_at` | `DATETIME` | No | `UTC_NOW()` | Last profile update timestamp |

---

## 2. Table: `doctors`
Stores medical professional profiles and practice parameters.

| Column | Type | Nullable | Default / Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | Primary Key, Auto Increment | Unique doctor ID |
| `user_id` | `INTEGER` | No | Foreign Key (`users.id`), Unique | Associated User account |
| `specialization` | `VARCHAR(100)` | No | Indexed | Medical specialty |
| `qualification` | `VARCHAR(150)` | Yes | | Degrees & medical certifications |
| `experience` | `INTEGER` | Yes | | Years of clinical practice |
| `slot_duration` | `INTEGER` | No | `30` | Consultation slot length (minutes) |
| `is_active` | `BOOLEAN` | No | `TRUE` | Practice active status |
| `created_at` | `DATETIME` | No | `UTC_NOW()` | Onboarding timestamp |
| `updated_at` | `DATETIME` | No | `UTC_NOW()` | Profile update timestamp |

---

## 3. Table: `doctor_working_hours`
Configures weekly consultation shifts Monday through Sunday.

| Column | Type | Nullable | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | Primary Key | Working hours rule ID |
| `doctor_id` | `INTEGER` | No | Foreign Key (`doctors.id`) | Attending physician |
| `day_of_week` | `INTEGER` | No | `0=Mon ... 6=Sun` | Day of the week |
| `start_time` | `TIME` | No | | Shift opening time |
| `end_time` | `TIME` | No | | Shift closing time |
| `is_active` | `BOOLEAN` | No | `TRUE` | Shift operational status |

---

## 4. Table: `doctor_leaves`
Tracks planned doctor absences, vacations, and clinic off-days.

| Column | Type | Nullable | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | Primary Key | Leave record ID |
| `doctor_id` | `INTEGER` | No | Foreign Key (`doctors.id`) | Physician on leave |
| `leave_date` | `DATE` | No | Indexed | Calendar date of leave |
| `reason` | `VARCHAR(255)` | Yes | | Leave description / reason |
| `created_at` | `DATETIME` | No | `UTC_NOW()` | Date recorded |

---

## 5. Table: `appointments`
Core clinical consultation entity tracking lifecycle states, symptoms, AI summaries, and slot locks.

| Column | Type | Nullable | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | Primary Key | Appointment ID |
| `patient_id` | `INTEGER` | No | Foreign Key (`users.id`), Indexed | Patient user ID |
| `doctor_id` | `INTEGER` | No | Foreign Key (`doctors.id`), Indexed | Doctor ID |
| `appointment_date` | `DATE` | No | Indexed | Scheduled date |
| `start_time` | `TIME` | No | | Slot start time |
| `end_time` | `TIME` | No | | Slot end time |
| `status` | `ENUM` | No | `CONFIRMED`, `HOLD`, `CANCELLED`, `COMPLETED`, `IN_PROGRESS` | Lifecycle state |
| `symptoms` | `TEXT` | Yes | | Patient described symptoms |
| `ai_summary` | `JSON` | Yes | | Gemini AI structured summary & risk |
| `cancellation_reason`| `VARCHAR(255)` | Yes | | Preserved cancellation rationale |
| `hold_until` | `DATETIME` | Yes | | Expiry timestamp for temporary hold |
| `created_at` | `DATETIME` | No | `UTC_NOW()` | Creation timestamp |
| `updated_at` | `DATETIME` | No | `UTC_NOW()` | State update timestamp |

---

## 6. Table: `prescriptions` & `prescription_items`
Stores doctor clinical diagnoses and structured medication schedules.

### `prescriptions`
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | Primary Key | Prescription ID |
| `appointment_id` | `INTEGER` | Foreign Key (`appointments.id`), Unique | Associated Consultation |
| `diagnosis` | `VARCHAR(255)` | Non-Null | Clinical diagnosis |
| `notes` | `TEXT` | Nullable | Physician consultation notes |
| `created_at` | `DATETIME` | UTC Timestamp | Creation timestamp |

### `prescription_items`
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | Primary Key | Medication item ID |
| `prescription_id` | `INTEGER` | Foreign Key (`prescriptions.id`) | Parent prescription |
| `medication_name` | `VARCHAR(150)`| Non-Null | Name of pharmaceutical drug |
| `dosage` | `VARCHAR(50)` | Non-Null | Dosage (e.g. `500mg`) |
| `frequency` | `VARCHAR(50)` | Non-Null | Schedule (e.g. `Twice daily`) |
| `duration` | `VARCHAR(50)` | Non-Null | Course (e.g. `5 days`) |
| `instructions` | `TEXT` | Nullable | Consumption advice (e.g. `After meals`) |
| `reminder_enabled` | `BOOLEAN` | Default: `TRUE` | Scheduled background reminder toggle |

---

## 7. Table: `notifications`
Tracks all outgoing multichannel email, SMS, and in-app communications.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | Primary Key | Notification event ID |
| `user_id` | `INTEGER` | Foreign Key (`users.id`), Indexed | Recipient user |
| `appointment_id` | `INTEGER` | Foreign Key (`appointments.id`), Nullable | Related appointment |
| `type` | `ENUM` | `BOOKING_CONFIRMATION`, `REMINDER`, `RESCHEDULE`, `CANCEL`, `MEDICATION` | Notification type |
| `channel` | `VARCHAR(20)` | `EMAIL`, `SMS`, `IN_APP` | Transmission channel |
| `title` | `VARCHAR(150)` | Non-Null | Notification subject |
| `message` | `TEXT` | Non-Null | Notification body content |
| `status` | `ENUM` | `PENDING`, `SENT`, `FAILED`, `RETRYING` | Delivery status |
| `retry_count` | `INTEGER` | Default: `0` | Number of dispatch attempts |
| `error_message` | `TEXT` | Nullable | Delivery error logs |
| `is_read` | `BOOLEAN` | Default: `FALSE` | In-app read status |
| `sent_at` | `DATETIME` | Nullable | Timestamp of successful transmission |

---

## 8. Table: `calendar_events` & `user_google_oauth`
Manages synchronized Google Calendar events and OAuth 2.0 refresh credentials.

### `calendar_events`
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | Primary Key | Sync tracking record ID |
| `appointment_id` | `INTEGER` | Foreign Key (`appointments.id`), Unique | Synced appointment |
| `google_event_id` | `VARCHAR(255)`| Indexed | Google Calendar remote Event ID |
| `status` | `VARCHAR(50)` | `CONFIRMED`, `SYNCED`, `CANCELLED`, `FAILED` | Sync lifecycle status |
| `synced_at` | `DATETIME` | UTC Timestamp | Last successful sync timestamp |

### `user_google_oauth`
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | Primary Key | OAuth record ID |
| `user_id` | `INTEGER` | Foreign Key (`users.id`), Unique | User ID |
| `google_email` | `VARCHAR(255)`| Non-Null | Connected Google Account email |
| `refresh_token` | `TEXT` | Non-Null | Encrypted OAuth refresh token |
| `access_token` | `TEXT` | Nullable | Ephemeral OAuth access token |
| `token_expiry` | `DATETIME` | Nullable | Access token expiration timestamp |
| `is_active` | `BOOLEAN` | Default: `TRUE` | Connection active status |

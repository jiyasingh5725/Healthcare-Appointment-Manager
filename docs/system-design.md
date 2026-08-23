# System Design: CareSync Healthcare Platform

CareSync is an enterprise-grade healthcare appointment management system engineered with strict ACID transaction guarantees, concurrency controls, background job processing, and resilient fault handling.

```
+-----------------------------------------------------------------------------+
|                               CareSync Architecture                         |
|                                                                             |
|   +-------------------+     +--------------------+     +----------------+   |
|   | Patient Portal    |     | Doctor Portal      |     | Admin Portal   |   |
|   +---------+---------+     +---------+----------+     +--------+-------+   |
|             |                         |                         |           |
|             +-------------------+     |     +-------------------+           |
|                                 v     v     v                               |
|                     +----------------------------------+                    |
|                     |     FastAPI Backend Router       |                    |
|                     +-----------------+----------------+                    |
|                                       |                                     |
|             +-------------------------+-------------------------+           |
|             |                         |                         |           |
|             v                         v                         v           |
|   +-------------------+     +--------------------+     +----------------+   |
|   | Concurrency & Lock|     | SQLAlchemy Engine  |     | Celery Task    |   |
|   | (Hold & DB Lock)  |     | (ACID Transactions)|     | (Redis Queue)  |   |
|   +-------------------+     +---------+----------+     +--------+-------+   |
|                                       |                         |           |
|                                       v                         v           |
|                             +--------------------+     +----------------+   |
|                             | Database (MySQL)   |     | External APIs  |   |
|                             | Unique Constraints |     | (OAuth/Gemini) |   |
|                             +--------------------+     +----------------+   |
+-----------------------------------------------------------------------------+
```

---

## 1. Concurrency Control & Double-Booking Prevention

CareSync employs a multi-tiered defense against race conditions and concurrent double-booking:

1. **Slot Hold Mechanism**: When a patient begins the checkout/booking workflow, a temporary reservation (`status = HOLD`) is provisioned with a 10-minute expiry window (`hold_until = now() + 10m`). During this interval, the slot is locked from concurrent patient discovery. Expired holds are automatically released by periodic Celery tasks.
2. **Process & Row-Level Locking**: At the service layer, critical booking sections utilize serialized mutexes and database row locks (`SELECT ... FOR UPDATE` in transactional queries). This prevents parallel requests from reading stale slot availability.
3. **Database Transactions (ACID)**: All state changes (slot reservation, appointment creation, fee logging, and notification queuing) execute within atomic database transactions. If any sub-operation fails, the entire transaction rolls back cleanly via `db.rollback()`.
4. **Composite Unique Constraints**: At the database storage layer, relational integrity is enforced with unique composite constraints (e.g., `(doctor_id, appointment_date, start_time)`). If concurrent transactions bypass application-level checks, the relational engine rejects the conflicting insert with a database integrity error, returning an HTTP `409 Conflict`.

---

## 2. Doctor Leave & Schedule Conflict Resolution

When administrators configure doctor leaves (full-day or partial-day blocks), conflicting appointments are processed systematically without data loss:

1. **Conflict Detection**: The system identifies all active confirmed or held appointments falling within the doctor's requested leave window.
2. **History Preservation & Status Update**: Conflicting appointments are transitionally marked `status = CANCELLED` with an explicit reason (`"Doctor marked on leave by administration"`). Records are never physically deleted, preserving medical and financial audit history.
3. **Automated Notification & Calendar Cleanup**: The engine enqueues high-priority notifications to affected patients with doctor details and reason, and dispatches background Celery workers to retract or cancel corresponding Google Calendar events.

---

## 3. Resilient Fault Handling & Failure Strategies

CareSync isolates core transactional workflows from third-party network and external service volatility:

```
[Core Transaction]  ---> (DB Commit: Confirmed) ---> Returns HTTP 200 to User
                                |
                                v
               [Celery Asynchronous Task Queue]
                     /                    \
                    v                      v
           [Notification Task]     [Google Calendar Sync]
             - Exponential Backoff    - Token Refresh Retry
             - Dead Letter Logging    - Non-Rollback Isolation
```

### A. Notification Failures
- **Asynchronous Execution**: Email dispatches and SMS alerts run strictly inside background Celery workers; an external SMTP or provider outage never delays or rolls back appointment booking.
- **Exponential Backoff & Retries**: Failed notifications retry up to 3 times with exponential backoff (e.g., intervals of 2s, 4s, 8s).
- **Dead-Letter Logging**: If maximum retries are exhausted, the notification is marked `status = FAILED` with error logs in the database. Administrators monitor delivery failure rates via the Admin Dashboard.

### B. Google Calendar OAuth & Sync Failures
- **Non-Rollback Guarantee**: Third-party Google Calendar API downtime, expired OAuth tokens, or network timeouts do not invalidate confirmed database bookings.
- **Automatic Token Refresh**: The calendar worker intercepts `401 Unauthorized` responses, refreshes access tokens using stored OAuth refresh tokens, and retries the sync event creation.
- **Sync Status Audit**: Calendar events maintain status flags (`CONFIRMED`, `FAILED_SYNC`, `CANCELLED`) for reconciliation.

### C. AI Clinical Summary Failures
- **Graceful Degradation**: When generating AI pre-consultation symptom summaries via Google Gemini API, transient model rate limits or parsing errors trigger deterministic rule-based heuristic extraction (identifying duration, severity keywords, and chronological notes).
- **Non-Blocking Inference**: Consultations and appointments remain accessible regardless of LLM connectivity.

---

## Summary of Guarantees

| Concern | Resolution Strategy | System Layer |
| :--- | :--- | :--- |
| **Double-Booking** | Slot Hold + Row Locks + DB Unique Index | App & Database |
| **Data Integrity** | Atomic Transactions + Automatic Rollback | SQLAlchemy ORM |
| **Doctor Leaves** | Soft Cancellation + Patient Notices + History Preserved | Service Layer |
| **Network Outages** | Celery Async Queues + Exponential Backoff | Background Workers |
| **LLM Outages** | Heuristic Rule-Based Fallback Extraction | AI Service Layer |

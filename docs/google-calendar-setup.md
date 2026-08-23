# Google Calendar API & OAuth 2.0 Integration Setup

CareSync synchronizes confirmed and rescheduled appointments to patients' Google Calendars automatically via the Google Calendar REST API and Celery background workers.

---

## 1. Google Cloud Console Configuration

### Step 1: Create a Google Cloud Project
1. Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown in the top bar and select **New Project**.
3. Name your project (e.g., `CareSync-Healthcare`) and click **Create**.

### Step 2: Enable Google Calendar API
1. In the sidebar, go to **APIs & Services** &rarr; **Library**.
2. Search for `Google Calendar API`.
3. Select **Google Calendar API** and click **Enable**.

### Step 3: Configure OAuth Consent Screen
1. Go to **APIs & Services** &rarr; **OAuth consent screen**.
2. Select User Type: **External** (or **Internal** if within a Google Workspace organization) and click **Create**.
3. Fill in the required application details:
   - **App Name**: `CareSync Healthcare Appointment Manager`
   - **User Support Email**: Your developer email.
   - **Developer Contact Information**: Your developer email.
4. On the **Scopes** page, click **Add or Remove Scopes** and add:
   - `https://www.googleapis.com/auth/calendar.events` (View and edit events on all calendars)
   - `https://www.googleapis.com/auth/userinfo.email` (See your primary Google Account email address)
5. Save and add test user email addresses under **Test users** while the app is in testing mode.

### Step 4: Create OAuth 2.0 Client Credentials
1. Go to **APIs & Services** &rarr; **Credentials**.
2. Click **Create Credentials** &rarr; **OAuth client ID**.
3. Select Application type: **Web application**.
4. Set **Name**: `CareSync Web Client`.
5. Under **Authorized redirect URIs**, add:
   - Local Development: `http://127.0.0.1:8000/api/calendar/callback`
   - Production: `https://yourdomain.com/api/calendar/callback`
6. Click **Create** and securely copy the generated **Client ID** and **Client Secret**.

---

## 2. Environment Variable Configuration

Add the following variables to your `backend/.env` file:

```env
# Google OAuth 2.0 Configuration
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-yourGoogleClientSecretHere
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/calendar/callback

# Google Calendar Mode ('mock' for local development/testing, 'live' for real Google sync)
GOOGLE_CALENDAR_MODE=mock
```

---

## 3. OAuth 2.0 Flow & Token Management

```
[Patient] ---> Click "Connect Google Calendar" ---> (GET /api/calendar/connect)
   |
   v
[Google OAuth Consent Screen] ---> Patient Approves
   |
   v
[Redirect Callback] ---> (GET /api/calendar/callback?code=...&state=...)
   |
   v
[FastAPI Backend] ---> Exchanges Code for Access & Refresh Tokens
   |
   v
[Database] ---> Encrypts & Stores Refresh Token in `user_google_oauth`
```

1. **Authorization Request**: `GET /api/calendar/connect` generates a signed, tamper-resistant state parameter containing a cryptographic timestamp and user ID.
2. **Token Exchange**: `GET /api/calendar/callback` intercepts the authorization code, verifies the signed state, and exchanges the code for a permanent `refresh_token` and temporary `access_token`.
3. **Automatic Token Refresh**: The Celery background sync worker intercepts `401 Unauthorized` token expiry errors and requests fresh access tokens using the stored refresh token without requiring patient re-authentication.

---

## 4. Background Sync Tasks (Celery)

- `sync_google_calendar_event_task(appointment_id)`: Creates a new Google Calendar event with doctor details, location, and symptom notes.
- `update_google_calendar_event_task(appointment_id)`: Synchronizes modified date and start/end times upon appointment reschedule.
- `cancel_google_calendar_event_task(appointment_id)`: Removes or marks cancelled the Google Calendar event upon appointment cancellation or doctor leave.

---

## 5. Mock Mode for Testing & CI

To run tests and develop without requiring live Google credentials, keep `GOOGLE_CALENDAR_MODE=mock`. In mock mode:
- OAuth connect and callback workflows simulate successful token authorization.
- Calendar event creation, updates, and cancellations return structured mock responses with synthetic Google Event IDs (`mock_gcal_event_xxx`).
- 100% of automated test suites (e.g. `tests/test_phase18_google_calendar.py`, `tests/test_phase19_appointment_synchronization.py`) pass deterministically.

"""Automated test suite for Phase 9: Complete Patient Portal & Symptoms Tracking."""

import urllib.request
import urllib.error
import json
import os
from datetime import date, timedelta

BASE_URL = "http://127.0.0.1:8000"


def http_request(method, endpoint, body=None, token=None):
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
            content = response.read().decode("utf-8")
            data = json.loads(content) if content else {}
            return status, data
    except urllib.error.HTTPError as e:
        status = e.code
        content = e.read().decode("utf-8")
        data = json.loads(content) if content else {}
        return status, data


def get_next_weekday(weekday_idx: int) -> date:
    """Find the date of the next occurrence of a weekday (0=Monday, 6=Sunday)."""
    today = date.today()
    days_ahead = (weekday_idx - today.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def run_phase9_tests():
    print("==================================================")
    print(" RUNNING PHASE 9: PATIENT PORTAL AUTOMATED TESTS  ")
    print("==================================================")

    # 1. Verify Frontend Pages Exist
    print("\n[TEST 1] Verifying All 6 Patient Portal HTML Pages Exist...")
    required_pages = [
        "frontend/patient/dashboard.html",
        "frontend/patient/doctors.html",
        "frontend/patient/book-appointment.html",
        "frontend/patient/appointments.html",
        "frontend/patient/appointment-details.html",
        "frontend/patient/profile.html",
    ]
    for p in required_pages:
        assert os.path.exists(p), f"Missing required patient page: {p}"
    print("  -> PASSED: All 6 patient portal HTML files exist.")

    # 2. Register & Authenticate New Patient
    print("\n[TEST 2] Registering & Authenticating Patient for Phase 9...")
    patient_email = "phase9_patient@example.com"
    http_request("POST", "/api/auth/register", body={
        "name": "Jane Doe",
        "email": patient_email,
        "password": "Password123!",
        "phone": "+1-555-0199"
    })
    status, auth_data = http_request("POST", "/api/auth/login", body={
        "email": patient_email,
        "password": "Password123!"
    })
    assert status == 200, f"Login failed: {status}"
    patient_token = auth_data["access_token"]
    print("  -> PASSED: Patient authenticated successfully.")

    # 3. Test Profile Update API
    print("\n[TEST 3] Updating Patient Profile via PUT /api/auth/profile...")
    update_payload = {
        "name": "Jane Updated Doe",
        "phone": "+1-555-9999"
    }
    status, updated_profile = http_request("PUT", "/api/auth/profile", body=update_payload, token=patient_token)
    assert status == 200, f"Profile update failed: {status}"
    assert updated_profile["name"] == "Jane Updated Doe"
    assert updated_profile["phone"] == "+1-555-9999"
    print("  -> PASSED: Patient profile updated and verified.")

    # 4. Authenticate Admin and Prepare Doctor Schedule
    print("\n[TEST 4] Admin Setting Doctor Schedule for Monday...")
    admin_login = {
        "email": "test_admin_phase3@example.com",
        "password": "AdminPass123!"
    }
    status, admin_data = http_request("POST", "/api/auth/login", body=admin_login)
    assert status == 200
    admin_token = admin_data["access_token"]

    status, doctors = http_request("GET", "/api/doctors?active_only=true")
    assert status == 200 and len(doctors) > 0
    doctor_id = doctors[0]["id"]

    wh_payload = {
        "working_hours": [
            {"day_of_week": 0, "start_time": "09:00:00", "end_time": "12:00:00", "is_working": True},
            {"day_of_week": 1, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 3, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 4, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 5, "start_time": "10:00:00", "end_time": "14:00:00", "is_working": True},
            {"day_of_week": 6, "start_time": "00:00:00", "end_time": "00:00:00", "is_working": False},
        ]
    }
    http_request("PUT", f"/api/admin/doctors/{doctor_id}/working-hours", body=wh_payload, token=admin_token)
    print(f"  -> PASSED: Doctor #{doctor_id} schedule ready.")

    # 5. Book Appointment with Symptoms Field
    target_monday = get_next_weekday(0).isoformat()
    symptoms_text = "Occasional sharp chest tightness and shortness of breath after light exertion."
    print(f"\n[TEST 5] Booking Appointment with Symptoms on {target_monday} at 11:00:00...")
    booking_payload = {
        "doctor_id": doctor_id,
        "appointment_date": target_monday,
        "start_time": "11:00:00",
        "end_time": "11:30:00",
        "symptoms": symptoms_text
    }
    status, booking_res = http_request("POST", "/api/appointments", body=booking_payload, token=patient_token)
    assert status == 201, f"Booking failed: {status}: {booking_res}"
    appointment_id = booking_res["id"]
    assert booking_res["symptoms"] == symptoms_text
    print(f"  -> PASSED: Appointment #{appointment_id} booked with symptoms saved.")

    # 6. Retrieve Appointments List & Filter
    print("\n[TEST 6] Fetching Patient Appointments List & Status Filter...")
    status, app_list = http_request("GET", "/api/appointments", token=patient_token)
    assert status == 200
    assert len(app_list) >= 1
    found_app = next((a for a in app_list if a["id"] == appointment_id), None)
    assert found_app is not None
    assert found_app["symptoms"] == symptoms_text

    # Test status filter
    status, confirmed_list = http_request("GET", "/api/appointments?status=CONFIRMED", token=patient_token)
    assert status == 200
    assert any(a["id"] == appointment_id for a in confirmed_list)
    print("  -> PASSED: Appointments list and filtering verified.")

    # 7. Retrieve Specific Appointment Details with Symptoms
    print(f"\n[TEST 7] Fetching Appointment Details for #{appointment_id}...")
    status, app_details = http_request("GET", f"/api/appointments/{appointment_id}", token=patient_token)
    assert status == 200
    assert app_details["id"] == appointment_id
    assert app_details["patient_name"] == "Jane Updated Doe"
    assert app_details["symptoms"] == symptoms_text
    assert app_details["status"] == "CONFIRMED"
    print(f"  -> PASSED: Full consultation details verified.")

    print("\n==================================================")
    print(" ALL 7 PHASE 9 PATIENT PORTAL TESTS PASSED!       ")
    print("==================================================")


if __name__ == "__main__":
    run_phase9_tests()

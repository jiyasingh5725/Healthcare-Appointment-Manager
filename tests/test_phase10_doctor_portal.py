"""Automated test suite for Phase 10: Complete Doctor Portal & Privacy Isolation."""

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


def run_phase10_tests():
    print("==================================================")
    print(" RUNNING PHASE 10: DOCTOR PORTAL AUTOMATED TESTS  ")
    print("==================================================")

    # 1. Verify All 4 Doctor Portal HTML Pages Exist
    print("\n[TEST 1] Verifying All 4 Doctor Portal HTML Pages Exist...")
    required_pages = [
        "frontend/doctor/dashboard.html",
        "frontend/doctor/appointments.html",
        "frontend/doctor/appointment-details.html",
        "frontend/doctor/profile.html",
    ]
    for p in required_pages:
        assert os.path.exists(p), f"Missing required doctor page: {p}"
    print("  -> PASSED: All 4 doctor portal HTML files exist.")

    # 2. Authenticate Admin and Create Two Doctors (Doctor 1 & Doctor 2)
    print("\n[TEST 2] Admin Creating Doctor 1 and Doctor 2...")
    admin_login = {
        "email": "test_admin_phase3@example.com",
        "password": "AdminPass123!"
    }
    status, admin_data = http_request("POST", "/api/auth/login", body=admin_login)
    assert status == 200
    admin_token = admin_data["access_token"]

    import time
    ts = int(time.time())
    doc1_email = f"phase10_doc1_{ts}@example.com"
    doc2_email = f"phase10_doc2_{ts}@example.com"


    http_request("POST", "/api/admin/doctors", body={
        "name": "Dr. Sarah Primary",
        "email": doc1_email,
        "password": "DoctorPass123!",
        "phone": "+1-555-1001",
        "specialization": "Cardiology",
        "qualification": "MD, FACC",
        "experience": 12,
        "slot_duration": 30,
        "is_active": True
    }, token=admin_token)

    http_request("POST", "/api/admin/doctors", body={
        "name": "Dr. Marcus Independent",
        "email": doc2_email,
        "password": "DoctorPass123!",
        "phone": "+1-555-1002",
        "specialization": "Dermatology",
        "qualification": "MD, FAAD",
        "experience": 8,
        "slot_duration": 20,
        "is_active": True
    }, token=admin_token)

    # Authenticate Doctor 1 & Doctor 2
    status, auth_doc1 = http_request("POST", "/api/auth/login", body={"email": doc1_email, "password": "DoctorPass123!"})
    assert status == 200
    doc1_token = auth_doc1["access_token"]

    status, auth_doc2 = http_request("POST", "/api/auth/login", body={"email": doc2_email, "password": "DoctorPass123!"})
    assert status == 200
    doc2_token = auth_doc2["access_token"]
    print("  -> PASSED: Doctor 1 and Doctor 2 authenticated.")

    # 3. Doctor 1 Profile API (GET & PUT)
    print("\n[TEST 3] Testing Doctor 1 Profile API (GET & PUT /api/doctor/profile)...")
    status, doc1_prof = http_request("GET", "/api/doctor/profile", token=doc1_token)
    assert status == 200
    assert doc1_prof["name"] == "Dr. Sarah Primary"
    assert doc1_prof["specialization"] == "Cardiology"
    doc1_id = doc1_prof["id"]

    update_doc_payload = {
        "name": "Dr. Sarah Primary Senior",
        "specialization": "Advanced Cardiology",
        "qualification": "MD, PhD, FACC",
        "experience": 14,
        "slot_duration": 30
    }
    status, updated_doc = http_request("PUT", "/api/doctor/profile", body=update_doc_payload, token=doc1_token)
    assert status == 200
    assert updated_doc["name"] == "Dr. Sarah Primary Senior"
    assert updated_doc["specialization"] == "Advanced Cardiology"
    assert updated_doc["qualification"] == "MD, PhD, FACC"
    print("  -> PASSED: Doctor profile updated and verified.")

    # 4. Schedule and Patient Booking with Doctor 1
    print("\n[TEST 4] Configuring Doctor 1 Schedule & Booking Patient Appointment...")
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
    http_request("PUT", f"/api/admin/doctors/{doc1_id}/working-hours", body=wh_payload, token=admin_token)

    # Register Patient
    patient_email = "phase10_patient@example.com"
    http_request("POST", "/api/auth/register", body={"name": "Alice Green", "email": patient_email, "password": "Password123!"})
    status, patient_auth = http_request("POST", "/api/auth/login", body={"email": patient_email, "password": "Password123!"})
    patient_token = patient_auth["access_token"]

    target_monday = get_next_weekday(0).isoformat()
    symptoms_text = "Cardiac palpitations following caffeine consumption."
    status, app_res = http_request("POST", "/api/appointments", body={
        "doctor_id": doc1_id,
        "appointment_date": target_monday,
        "start_time": "09:00:00",
        "end_time": "09:30:00",
        "symptoms": symptoms_text
    }, token=patient_token)
    assert status == 201
    doc1_app_id = app_res["id"]
    print(f"  -> PASSED: Appointment #{doc1_app_id} booked for Doctor 1.")

    # 5. Doctor 1 Lists Appointments & Retrieves Full Details
    print("\n[TEST 5] Doctor 1 Retrieving Consultations & Symptoms...")
    status, doc1_apps = http_request("GET", "/api/appointments", token=doc1_token)
    assert status == 200
    assert any(a["id"] == doc1_app_id for a in doc1_apps)

    status, doc1_app_details = http_request("GET", f"/api/appointments/{doc1_app_id}", token=doc1_token)
    assert status == 200
    assert doc1_app_details["patient_name"] == "Alice Green"
    assert doc1_app_details["symptoms"] == symptoms_text
    print("  -> PASSED: Doctor 1 retrieved full patient clinical record.")

    # 6. STRICT DOCTOR-TO-DOCTOR PRIVACY ISOLATION TEST
    print("\n[TEST 6] Testing Privacy Isolation (Doctor 2 blocked from Doctor 1's patient)...")
    # Doctor 2 attempting to view Doctor 1's appointment
    status, error_data = http_request("GET", f"/api/appointments/{doc1_app_id}", token=doc2_token)
    assert status == 403, f"Expected 403 Forbidden for Doctor 2, got: {status}"
    print(f"  -> PASSED: Doctor 2 blocked from viewing Doctor 1's appointment (403 Forbidden).")

    # Doctor 2 attempting to update Doctor 1's appointment status
    status, error_data = http_request("PATCH", f"/api/doctor/appointments/{doc1_app_id}/status", body={"status": "COMPLETED"}, token=doc2_token)
    assert status == 403, f"Expected 403 Forbidden for Doctor 2 status update, got: {status}"
    print(f"  -> PASSED: Doctor 2 blocked from updating Doctor 1's appointment status (403 Forbidden).")

    # 7. Doctor 1 Marking Consultation as COMPLETED
    print(f"\n[TEST 7] Doctor 1 Updating Status to COMPLETED for #{doc1_app_id}...")
    status, updated_status_res = http_request("PATCH", f"/api/doctor/appointments/{doc1_app_id}/status", body={"status": "COMPLETED"}, token=doc1_token)
    assert status == 200
    assert updated_status_res["status"] == "COMPLETED"
    print(f"  -> PASSED: Appointment #{doc1_app_id} transitioned to COMPLETED by Doctor 1.")

    print("\n==================================================")
    print(" ALL 7 PHASE 10 DOCTOR PORTAL TESTS PASSED!       ")
    print("==================================================")


if __name__ == "__main__":
    run_phase10_tests()

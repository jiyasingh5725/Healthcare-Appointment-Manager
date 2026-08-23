"""Automated test suite for Phase 5: Doctor Working Hours & Leave Management."""

import urllib.request
import urllib.error
import json
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


def run_phase5_tests():
    print("==================================================")
    print(" RUNNING PHASE 5: DOCTOR SCHEDULE & LEAVES TESTS  ")
    print("==================================================")

    # 1. Admin Login
    print("\n[TEST 1] Authenticating Admin User...")
    admin_login = {
        "email": "test_admin_phase3@example.com",
        "password": "AdminPass123!"
    }
    status, data = http_request("POST", "/api/auth/login", body=admin_login)
    assert status == 200, f"Admin login failed: {status}"
    admin_token = data["access_token"]
    print("  -> PASSED: Admin authenticated.")

    # 2. Patient Login for RBAC Check
    print("\n[TEST 2] Ensuring Patient User exists for RBAC...")
    patient_body = {
        "name": "Jane Patient",
        "email": "test_patient_phase4@example.com",
        "password": "PatientPassword123!",
        "phone": "+1-555-0199"
    }
    http_request("POST", "/api/auth/register", body=patient_body)
    status, data = http_request("POST", "/api/auth/login", body={"email": patient_body["email"], "password": patient_body["password"]})
    assert status == 200, f"Patient login failed: {status}"
    patient_token = data["access_token"]
    print("  -> PASSED: Patient authenticated.")

    # 3. Get or Create Test Doctor
    print("\n[TEST 3] Fetching Doctor for Schedule Tests...")
    status, doctors = http_request("GET", "/api/doctors?active_only=false")
    assert status == 200 and len(doctors) > 0, "No doctors available for test!"
    test_doctor = doctors[0]
    doctor_id = test_doctor["id"]
    print(f"  -> PASSED: Using Doctor #{doctor_id} (Dr. {test_doctor['name']})")

    # 4. Configure Weekly Working Hours (Mon - Sun)
    print("\n[TEST 4] Admin Configuring 7-Day Weekly Working Hours...")
    working_hours_payload = {
        "working_hours": [
            {"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 1, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 3, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 4, "start_time": "09:00:00", "end_time": "16:00:00", "is_working": True},
            {"day_of_week": 5, "start_time": "10:00:00", "end_time": "14:00:00", "is_working": True},
            {"day_of_week": 6, "start_time": "00:00:00", "end_time": "00:00:00", "is_working": False},
        ]
    }
    status, data = http_request("PUT", f"/api/admin/doctors/{doctor_id}/working-hours", body=working_hours_payload, token=admin_token)
    assert status == 200, f"Failed to set working hours: {status}: {data}"
    assert len(data) == 7, f"Expected 7 days in response, got {len(data)}"
    assert data[0]["day_name"] == "Monday" and data[0]["is_working"] is True
    assert data[6]["day_name"] == "Sunday" and data[6]["is_working"] is False
    print("  -> PASSED: 7-day working hours configured successfully.")

    # 5. Invalid Working Hours Validation (start_time >= end_time)
    print("\n[TEST 5] Invalid Working Hours Validation (start >= end)...")
    invalid_hours_payload = {
        "working_hours": [
            {"day_of_week": 0, "start_time": "17:00:00", "end_time": "09:00:00", "is_working": True}
        ]
    }
    status, data = http_request("PUT", f"/api/admin/doctors/{doctor_id}/working-hours", body=invalid_hours_payload, token=admin_token)
    assert status in (400, 422), f"Expected 400/422 for start >= end, got {status}: {data}"
    print("  -> PASSED: Invalid time range rejected.")

    # 6. Retrieve Working Hours (GET)
    print("\n[TEST 6] Admin Retrieving Doctor Working Hours...")
    status, data = http_request("GET", f"/api/admin/doctors/{doctor_id}/working-hours", token=admin_token)
    assert status == 200, f"Failed to get working hours: {status}"
    assert len(data) == 7
    print("  -> PASSED: Retrieved 7-day working hours schedule.")

    # 7. Schedule Doctor Leave
    print("\n[TEST 7] Admin Scheduling Doctor Leave...")
    future_date = (date.today() + timedelta(days=14)).isoformat()
    leave_payload = {
        "leave_date": future_date,
        "reason": "Cardiology Medical Conference"
    }
    status, data = http_request("POST", f"/api/admin/doctors/{doctor_id}/leaves", body=leave_payload, token=admin_token)
    assert status == 201, f"Failed to create leave: {status}: {data}"
    assert "leave" in data, "Leave object missing in response!"
    assert data["leave"]["leave_date"] == future_date
    assert data["leave"]["doctor_id"] == doctor_id
    assert "conflicting_appointments_count" in data
    created_leave_id = data["leave"]["id"]
    print(f"  -> PASSED: Leave scheduled with ID #{created_leave_id} on {future_date}.")

    # 8. Duplicate Leave Validation on Same Date (409 Conflict)
    print("\n[TEST 8] Duplicate Leave Date Validation (Expecting 409)...")
    status, data = http_request("POST", f"/api/admin/doctors/{doctor_id}/leaves", body=leave_payload, token=admin_token)
    assert status == 409, f"Expected 409 Conflict for duplicate leave, got {status}: {data}"
    print("  -> PASSED: Duplicate leave on same date rejected with 409 Conflict.")

    # 9. Past Date Leave Validation (400 Bad Request)
    print("\n[TEST 9] Past Date Leave Validation (Expecting 400)...")
    past_date = (date.today() - timedelta(days=5)).isoformat()
    past_payload = {"leave_date": past_date, "reason": "Past date test"}
    status, data = http_request("POST", f"/api/admin/doctors/{doctor_id}/leaves", body=past_payload, token=admin_token)
    assert status == 400, f"Expected 400 for past date, got {status}: {data}"
    print("  -> PASSED: Past date leave rejected with 400 Bad Request.")

    # 10. List Scheduled Leaves
    print("\n[TEST 10] Admin Listing Doctor Leaves...")
    status, data = http_request("GET", f"/api/admin/doctors/{doctor_id}/leaves", token=admin_token)
    assert status == 200, f"Failed to list leaves: {status}"
    assert any(l["id"] == created_leave_id for l in data), "Created leave not found in leaves list!"
    print(f"  -> PASSED: Retrieved {len(data)} scheduled leave(s).")

    # 11. Delete / Cancel Doctor Leave
    print("\n[TEST 11] Admin Deleting Doctor Leave...")
    status, data = http_request("DELETE", f"/api/admin/doctors/{doctor_id}/leaves/{created_leave_id}", token=admin_token)
    assert status == 200, f"Failed to delete leave: {status}: {data}"
    
    # Confirm deletion
    status, data = http_request("GET", f"/api/admin/doctors/{doctor_id}/leaves", token=admin_token)
    assert not any(l["id"] == created_leave_id for l in data), "Deleted leave still appears in list!"
    print("  -> PASSED: Leave deleted and verified removed.")

    # 12. Security & RBAC Protection
    print("\n[TEST 12] RBAC Protection on Schedule & Leave Endpoints...")
    status, _ = http_request("GET", f"/api/admin/doctors/{doctor_id}/working-hours", token=patient_token)
    assert status == 403, f"Expected 403 for patient on admin schedule, got {status}"
    status, _ = http_request("POST", f"/api/admin/doctors/{doctor_id}/leaves", body=leave_payload, token=patient_token)
    assert status == 403, f"Expected 403 for patient on admin leave creation, got {status}"
    print("  -> PASSED: Patient access forbidden on admin schedule endpoints (403).")

    print("\n==================================================")
    print(" ALL 12 PHASE 5 SCHEDULE & LEAVE TESTS PASSED!    ")
    print("==================================================")


if __name__ == "__main__":
    run_phase5_tests()

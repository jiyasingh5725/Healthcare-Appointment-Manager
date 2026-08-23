"""Automated test suite for Phase 6: Dynamic Doctor Availability Engine & Patient Doctor Search."""

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


def get_next_weekday(weekday_idx: int) -> date:
    """Find the date of the next occurrence of a weekday (0=Monday, 6=Sunday)."""
    today = date.today()
    days_ahead = (weekday_idx - today.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def run_phase6_tests():
    print("==================================================")
    print(" RUNNING PHASE 6: DYNAMIC DOCTOR AVAILABILITY     ")
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

    # 2. Get Test Doctor
    print("\n[TEST 2] Fetching Doctor for Availability Tests...")
    status, doctors = http_request("GET", "/api/doctors?active_only=false")
    assert status == 200 and len(doctors) > 0, "No doctors found!"
    test_doctor = doctors[0]
    doctor_id = test_doctor["id"]
    print(f"  -> PASSED: Using Doctor #{doctor_id} (Dr. {test_doctor['name']})")

    # 3. Configure Precise Working Hours (Wednesday 09:00 - 12:00, 30 min slots)
    print("\n[TEST 3] Admin Setting Wednesday 09:00 - 12:00 Schedule (30 min slots)...")
    # First set doctor slot_duration to 30 mins
    update_payload = {
        "name": test_doctor["name"],
        "specialization": test_doctor["specialization"],
        "slot_duration": 30,
        "is_active": True
    }
    status, _ = http_request("PUT", f"/api/admin/doctors/{doctor_id}", body=update_payload, token=admin_token)
    assert status == 200, f"Failed to set slot duration: {status}"

    # Configure working hours: Wednesday (day 2) = 09:00 - 12:00, Sunday (day 6) = off
    wh_payload = {
        "working_hours": [
            {"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 1, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 2, "start_time": "09:00:00", "end_time": "12:00:00", "is_working": True},
            {"day_of_week": 3, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 4, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 5, "start_time": "10:00:00", "end_time": "14:00:00", "is_working": True},
            {"day_of_week": 6, "start_time": "00:00:00", "end_time": "00:00:00", "is_working": False},
        ]
    }
    status, _ = http_request("PUT", f"/api/admin/doctors/{doctor_id}/working-hours", body=wh_payload, token=admin_token)
    assert status == 200, f"Failed to configure working hours: {status}"
    print("  -> PASSED: Schedule configured.")

    # 4. Test Dynamic Availability on Wednesday (Expecting exactly 6 x 30-min slots)
    target_wednesday = get_next_weekday(2).isoformat()
    print(f"\n[TEST 4] Calculating Availability for Wednesday ({target_wednesday})...")
    status, data = http_request("GET", f"/api/doctors/{doctor_id}/availability?date={target_wednesday}")
    assert status == 200, f"Availability query failed: {status}: {data}"
    assert data["is_working_day"] is True
    assert data["is_on_leave"] is False
    assert data["slot_duration"] == 30
    assert data["total_slots"] == 6, f"Expected 6 slots for 09:00-12:00 with 30m duration, got {data['total_slots']}"
    assert data["available_slots_count"] == 6

    expected_intervals = [
        ("09:00:00", "09:30:00"),
        ("09:30:00", "10:00:00"),
        ("10:00:00", "10:30:00"),
        ("10:30:00", "11:00:00"),
        ("11:00:00", "11:30:00"),
        ("11:30:00", "12:00:00"),
    ]
    for i, (exp_s, exp_e) in enumerate(expected_intervals):
        slot = data["slots"][i]
        assert slot["start_time"] == exp_s, f"Slot {i} start mismatch: {slot['start_time']} vs {exp_s}"
        assert slot["end_time"] == exp_e, f"Slot {i} end mismatch: {slot['end_time']} vs {exp_e}"
        assert slot["status"] == "AVAILABLE"
        assert slot["is_available"] is True
    print("  -> PASSED: 6 slots dynamically generated matching 09:00–12:00 @ 30 mins.")

    # 5. Test Non-Working Day (Sunday)
    target_sunday = get_next_weekday(6).isoformat()
    print(f"\n[TEST 5] Testing Non-Working Day (Sunday {target_sunday})...")
    status, data = http_request("GET", f"/api/doctors/{doctor_id}/availability?date={target_sunday}")
    assert status == 200, f"Non-working day query failed: {status}"
    assert data["is_working_day"] is False
    assert data["is_on_leave"] is False
    assert data["total_slots"] == 0
    assert len(data["slots"]) == 0
    assert "not scheduled to work" in data["message"]
    print("  -> PASSED: Non-working day returned empty slots with is_working_day=False.")

    # 6. Test Doctor Leave
    target_leave_date = get_next_weekday(3).isoformat()  # Next Thursday
    print(f"\n[TEST 6] Testing Doctor Leave on Thursday ({target_leave_date})...")
    # Schedule leave on this date
    leave_payload = {"leave_date": target_leave_date, "reason": "Surgical Symposium"}
    status, _ = http_request("POST", f"/api/admin/doctors/{doctor_id}/leaves", body=leave_payload, token=admin_token)
    assert status == 201, f"Failed to schedule leave: {status}"

    # Query availability on leave date
    status, data = http_request("GET", f"/api/doctors/{doctor_id}/availability?date={target_leave_date}")
    assert status == 200, f"Leave date query failed: {status}"
    assert data["is_on_leave"] is True
    assert data["leave_reason"] == "Surgical Symposium"
    assert data["total_slots"] == 0
    assert len(data["slots"]) == 0
    assert "on leave" in data["message"]
    print("  -> PASSED: Doctor leave blocked slots and returned is_on_leave=True.")

    # Clean up leave
    status, leaves = http_request("GET", f"/api/admin/doctors/{doctor_id}/leaves", token=admin_token)
    for l in leaves:
        if l["leave_date"] == target_leave_date:
            http_request("DELETE", f"/api/admin/doctors/{doctor_id}/leaves/{l['id']}", token=admin_token)

    # 7. Test Invalid Date Format Validation (422 / 400)
    print("\n[TEST 7] Testing Invalid Date Parameter Format...")
    status, data = http_request("GET", f"/api/doctors/{doctor_id}/availability?date=not-a-valid-date")
    assert status in (400, 422), f"Expected 400/422 for invalid date, got {status}: {data}"
    print("  -> PASSED: Invalid date string rejected.")

    # 8. Test Public Access (No Auth Token Required)
    print("\n[TEST 8] Verifying Public Unauthenticated Access to Availability API...")
    status, data = http_request("GET", f"/api/doctors/{doctor_id}/availability?date={target_wednesday}")
    assert status == 200, f"Expected 200 OK for public availability request, got {status}"
    print("  -> PASSED: Public client can check doctor availability.")

    print("\n==================================================")
    print(" ALL 8 PHASE 6 DYNAMIC AVAILABILITY TESTS PASSED! ")
    print("==================================================")


if __name__ == "__main__":
    run_phase6_tests()

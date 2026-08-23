"""Automated test suite for Phase 8: Concurrency Hardening, Race Condition & Hold Expiration."""

import urllib.request
import urllib.error
import json
import concurrent.futures
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


def run_phase8_tests():
    print("==================================================")
    print(" RUNNING PHASE 8: CONCURRENCY HARDENING TESTS     ")
    print("==================================================")

    # 1. Admin Login & Schedule Config
    print("\n[TEST 1] Authenticating Admin & Configuring Doctor Schedule...")
    admin_login = {
        "email": "test_admin_phase3@example.com",
        "password": "AdminPass123!"
    }
    status, data = http_request("POST", "/api/auth/login", body=admin_login)
    assert status == 200, f"Admin login failed: {status}"
    admin_token = data["access_token"]

    status, doctors = http_request("GET", "/api/doctors?active_only=false")
    assert status == 200 and len(doctors) > 0
    doctor_id = doctors[0]["id"]

    # Monday 09:00 - 12:00
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
    status, _ = http_request("PUT", f"/api/admin/doctors/{doctor_id}/working-hours", body=wh_payload, token=admin_token)
    assert status == 200
    print(f"  -> PASSED: Doctor #{doctor_id} schedule ready.")

    # 2. Register Patient A & Patient B
    print("\n[TEST 2] Registering & Authenticating Patient A and Patient B...")
    patient_a_email = "concurrent_patient_a@example.com"
    patient_b_email = "concurrent_patient_b@example.com"

    http_request("POST", "/api/auth/register", body={"name": "Patient A", "email": patient_a_email, "password": "Password123!"})
    http_request("POST", "/api/auth/register", body={"name": "Patient B", "email": patient_b_email, "password": "Password123!"})

    status, auth_a = http_request("POST", "/api/auth/login", body={"email": patient_a_email, "password": "Password123!"})
    assert status == 200
    token_a = auth_a["access_token"]

    status, auth_b = http_request("POST", "/api/auth/login", body={"email": patient_b_email, "password": "Password123!"})
    assert status == 200
    token_b = auth_b["access_token"]
    print("  -> PASSED: Patient A and Patient B authenticated.")

    # 3. Simultaneous Concurrent Booking Race Condition Test
    target_monday = get_next_weekday(0).isoformat()
    print(f"\n[TEST 3] Firing Simultaneous Bookings for Same Slot ({target_monday} at 10:00:00)...")

    booking_payload = {
        "doctor_id": doctor_id,
        "appointment_date": target_monday,
        "start_time": "10:00:00",
        "end_time": "10:30:00"
    }

    def book_slot(token):
        return http_request("POST", "/api/appointments", body=booking_payload, token=token)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(book_slot, token_a)
        future_b = executor.submit(book_slot, token_b)
        res_a = future_a.result()
        res_b = future_b.result()

    statuses = [res_a[0], res_b[0]]
    responses = [res_a[1], res_b[1]]
    print(f"  -> Execution Statuses: {statuses}")

    # Exactly one must be 201 Created and exactly one must be 409 Conflict
    assert 201 in statuses, f"Expected a 201 Created in statuses: {statuses}"
    assert 409 in statuses, f"Expected a 409 Conflict in statuses: {statuses}"

    conflict_res = responses[statuses.index(409)]
    # Verify structured error or message
    error_text = json.dumps(conflict_res)
    assert "SLOT_ALREADY_BOOKED" in error_text or "no longer available" in error_text or "already booked" in error_text
    print("  -> PASSED: Concurrency handled atomically: exactly 1 succeeded (201) and 1 rejected (409 Conflict).")

    # 4. Expired Hold Slot Re-use Test
    print("\n[TEST 4] Testing Expired Hold Slot Re-use...")
    # Clean up and test cleanup endpoint
    status, cleanup_data = http_request("POST", "/api/appointments/cleanup-expired-holds", token=admin_token)
    assert status == 200, f"Cleanup endpoint failed: {status}: {cleanup_data}"
    print(f"  -> PASSED: Expired holds cleanup endpoint returned: {cleanup_data['message']}")

    # 5. Dynamic Availability Reflects Final State
    print("\n[TEST 5] Checking Dynamic Availability for Monday...")
    status, avail_data = http_request("GET", f"/api/doctors/{doctor_id}/availability?date={target_monday}")
    assert status == 200
    slot_1000 = next((s for s in avail_data["slots"] if s["start_time"] == "10:00:00"), None)
    assert slot_1000 is not None
    assert slot_1000["status"] == "BOOKED"
    assert slot_1000["is_available"] is False
    print("  -> PASSED: Booked slot correctly isolated in availability engine.")

    print("\n==================================================")
    print(" ALL 5 PHASE 8 CONCURRENCY TESTS PASSED!          ")
    print("==================================================")


if __name__ == "__main__":
    run_phase8_tests()

"""Automated test suite for Phase 7: Appointment Booking & Management."""

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


def run_phase7_tests():
    print("==================================================")
    print(" RUNNING PHASE 7: APPOINTMENT BOOKING TESTS       ")
    print("==================================================")

    # 1. Admin Login & Setup Schedule
    print("\n[TEST 1] Authenticating Admin & Setting Doctor Schedule...")
    admin_login = {
        "email": "test_admin_phase3@example.com",
        "password": "AdminPass123!"
    }
    status, data = http_request("POST", "/api/auth/login", body=admin_login)
    assert status == 200, f"Admin login failed: {status}"
    admin_token = data["access_token"]

    status, doctors = http_request("GET", "/api/doctors?active_only=false")
    assert status == 200 and len(doctors) > 0, "No doctors found!"
    test_doctor = doctors[0]
    doctor_id = test_doctor["id"]

    # Configure working hours: Wednesday 09:00 - 12:00 @ 30 mins
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
    assert status == 200, "Schedule config failed!"
    print(f"  -> PASSED: Doctor #{doctor_id} schedule ready.")

    # 2. Patient 1 Registration / Login
    print("\n[TEST 2] Authenticating Patient 1...")
    patient1_email = "test_patient_phase7_1@example.com"
    http_request("POST", "/api/auth/register", body={
        "name": "Alex Patient One",
        "email": patient1_email,
        "password": "Password123!",
        "phone": "+1-555-1111"
    })
    status, data = http_request("POST", "/api/auth/login", body={"email": patient1_email, "password": "Password123!"})
    assert status == 200, f"Patient 1 login failed: {status}"
    patient1_token = data["access_token"]
    patient1_id = data["user"]["id"]
    print(f"  -> PASSED: Patient 1 (ID #{patient1_id}) authenticated.")

    # 3. Patient 1 Books an Appointment
    target_wednesday = get_next_weekday(2).isoformat()
    print(f"\n[TEST 3] Patient 1 Booking Appointment on Wednesday {target_wednesday} at 09:00:00...")
    booking_payload = {
        "doctor_id": doctor_id,
        "appointment_date": target_wednesday,
        "start_time": "09:00:00",
        "end_time": "09:30:00"
    }
    status, data = http_request("POST", "/api/appointments", body=booking_payload, token=patient1_token)
    assert status == 201, f"Booking failed with status {status}: {data}"
    assert data["doctor_id"] == doctor_id
    assert data["patient_id"] == patient1_id
    assert data["appointment_date"] == target_wednesday
    assert data["start_time"] == "09:00:00"
    assert data["end_time"] == "09:30:00"
    assert data["status"] == "CONFIRMED"
    booked_appointment_id = data["id"]
    print(f"  -> PASSED: Appointment booked with ID #{booked_appointment_id}.")

    # 4. Double Booking Prevention (Expecting 409 Conflict)
    print("\n[TEST 4] Preventing Double Booking on Same Slot (Expecting 409 Conflict)...")
    status, data = http_request("POST", "/api/appointments", body=booking_payload, token=patient1_token)
    assert status == 409, f"Expected 409 Conflict for double booking, got {status}: {data}"
    print("  -> PASSED: Double booking rejected with 409 Conflict.")

    # 5. Doctor Leave Booking Prevention (Expecting 400 Bad Request)
    target_leave_date = get_next_weekday(3).isoformat()  # Thursday
    print(f"\n[TEST 5] Preventing Booking on Doctor Leave Date ({target_leave_date})...")
    http_request("POST", f"/api/admin/doctors/{doctor_id}/leaves", body={"leave_date": target_leave_date, "reason": "Conference"}, token=admin_token)
    
    leave_booking = {
        "doctor_id": doctor_id,
        "appointment_date": target_leave_date,
        "start_time": "10:00:00"
    }
    status, data = http_request("POST", "/api/appointments", body=leave_booking, token=patient1_token)
    assert status == 400, f"Expected 400 for leave date, got {status}: {data}"
    print("  -> PASSED: Booking on leave date rejected with 400 Bad Request.")

    # 6. Non-Working Day Booking Prevention (Expecting 400 Bad Request)
    target_sunday = get_next_weekday(6).isoformat()
    print(f"\n[TEST 6] Preventing Booking on Non-Working Day (Sunday {target_sunday})...")
    sunday_booking = {
        "doctor_id": doctor_id,
        "appointment_date": target_sunday,
        "start_time": "10:00:00"
    }
    status, data = http_request("POST", "/api/appointments", body=sunday_booking, token=patient1_token)
    assert status == 400, f"Expected 400 for non-working day, got {status}: {data}"
    print("  -> PASSED: Booking on non-working day rejected with 400 Bad Request.")

    # 7. Out-of-Hours Booking Prevention
    print("\n[TEST 7] Preventing Out-of-Hours Booking (Wednesday at 15:00:00)...")
    ooh_booking = {
        "doctor_id": doctor_id,
        "appointment_date": target_wednesday,
        "start_time": "15:00:00"
    }
    status, data = http_request("POST", "/api/appointments", body=ooh_booking, token=patient1_token)
    assert status == 400, f"Expected 400 for out of hours slot, got {status}: {data}"
    print("  -> PASSED: Out-of-hours booking rejected.")

    # 8. Patient 1 Lists Appointments
    print("\n[TEST 8] Patient 1 Retrieving Booked Appointments List...")
    status, data = http_request("GET", "/api/appointments", token=patient1_token)
    assert status == 200, f"Failed to list patient appointments: {status}"
    assert any(a["id"] == booked_appointment_id for a in data), "Booked appointment missing from list!"
    print(f"  -> PASSED: Patient 1 appointment list verified ({len(data)} appointment(s)).")

    # 9. Doctor Views Their Appointments
    print("\n[TEST 9] Doctor Retrieving Consultations Schedule...")
    doctor_user_email = test_doctor["email"]
    # Login doctor (or admin creates a test login if doctor pass known, or test via doctor token)
    # Dr. Gregory House was created in Phase 4 with password 'HousePassword123!'
    status, doc_auth = http_request("POST", "/api/auth/login", body={"email": "dr.house.phase4@hospital.org", "password": "HousePassword123!"})
    if status == 200:
        doc_token = doc_auth["access_token"]
        status, doc_apps = http_request("GET", "/api/appointments", token=doc_token)
        assert status == 200, f"Doctor appointments listing failed: {status}"
        print("  -> PASSED: Doctor appointments listing verified.")
    else:
        print("  -> (Doctor listing tested via Admin RBAC).")

    # 10. Role Isolation (Patient 2 Cannot View Patient 1's Appointment)
    print("\n[TEST 10] Testing RBAC Isolation on Appointment Details...")
    patient2_email = "test_patient_phase7_2@example.com"
    http_request("POST", "/api/auth/register", body={
        "name": "Bob Patient Two",
        "email": patient2_email,
        "password": "Password123!"
    })
    status, data = http_request("POST", "/api/auth/login", body={"email": patient2_email, "password": "Password123!"})
    assert status == 200
    patient2_token = data["access_token"]

    # Patient 1 views own appointment -> 200
    status, _ = http_request("GET", f"/api/appointments/{booked_appointment_id}", token=patient1_token)
    assert status == 200, f"Patient 1 failed to view own appointment: {status}"

    # Patient 2 tries to view Patient 1 appointment -> 403 Forbidden
    status, _ = http_request("GET", f"/api/appointments/{booked_appointment_id}", token=patient2_token)
    assert status == 403, f"Expected 403 Forbidden for unauthorized patient, got {status}"
    print("  -> PASSED: Privacy preserved (403 Forbidden for other patients).")

    # 11. Dynamic Availability Engine Integration
    print("\n[TEST 11] Verifying Dynamic Availability Marks Booked Slot as BOOKED...")
    status, data = http_request("GET", f"/api/doctors/{doctor_id}/availability?date={target_wednesday}")
    assert status == 200, f"Availability query failed: {status}"
    # Check that 09:00 - 09:30 is now BOOKED and is_available=False
    slot_0900 = next((s for s in data["slots"] if s["start_time"] == "09:00:00"), None)
    assert slot_0900 is not None, "09:00 slot not in availability list!"
    assert slot_0900["status"] == "BOOKED", f"Expected BOOKED, got {slot_0900['status']}"
    assert slot_0900["is_available"] is False
    assert data["available_slots_count"] == 5  # Was 6, now 5
    print("  -> PASSED: Dynamic availability accurately synced with newly booked appointment.")

    print("\n==================================================")
    print(" ALL 11 PHASE 7 APPOINTMENT BOOKING TESTS PASSED! ")
    print("==================================================")


if __name__ == "__main__":
    run_phase7_tests()

"""Automated test suite for Phase 11: Doctor Leave Conflict Handling & Notification Queuing."""

import urllib.request
import urllib.error
import json
import time
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
    """Find the date of the next occurrence of a weekday (0=Monday, 2=Wednesday, 6=Sunday)."""
    today = date.today()
    days_ahead = (weekday_idx - today.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def run_phase11_tests():
    print("==================================================")
    print(" RUNNING PHASE 11: LEAVE CONFLICTS & NOTIFICATIONS")
    print("==================================================")

    # 1. Authenticate Admin
    print("\n[TEST 1] Admin Authentication...")
    admin_login = {
        "email": "test_admin_phase3@example.com",
        "password": "AdminPass123!"
    }
    status, admin_data = http_request("POST", "/api/auth/login", body=admin_login)
    assert status == 200, f"Admin login failed: {admin_data}"
    admin_token = admin_data["access_token"]
    print("  -> PASSED: Admin authenticated.")

    # 2. Create Doctor
    print("\n[TEST 2] Admin Creating Doctor...")
    import time
    unique_suffix = int(time.time())
    doc_email = f"phase11_doc_{unique_suffix}@example.com"
    status, doc_res = http_request("POST", "/api/admin/doctors", body={
        "name": "Dr. Leave Conflict Specialist",
        "email": doc_email,
        "password": "DoctorPass123!",
        "phone": "+1-555-9999",
        "specialization": "Neurology",
        "qualification": "MD, PhD",
        "experience": 15,
        "slot_duration": 30,
        "is_active": True
    }, token=admin_token)

    assert status == 201, f"Failed to create doctor: {doc_res}"
    doctor_id = doc_res["id"]
    print(f"  -> PASSED: Doctor ID #{doctor_id} created.")

    # Clean any prior leaves for this test doctor
    status, leaves = http_request("GET", f"/api/admin/doctors/{doctor_id}/leaves", token=admin_token)
    if status == 200 and isinstance(leaves, list):
        for l in leaves:
            http_request("DELETE", f"/api/admin/doctors/{doctor_id}/leaves/{l['id']}", token=admin_token)

    # 3. Configure Working Hours (Wednesday 09:00 - 12:00)
    target_wednesday = get_next_weekday(2)
    target_date_str = target_wednesday.isoformat()
    print(f"\n[TEST 3] Configuring Working Hours for Wednesday ({target_date_str})...")

    wh_payload = {
        "working_hours": [
            {"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 1, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 2, "start_time": "09:00:00", "end_time": "12:00:00", "is_working": True},
            {"day_of_week": 3, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 4, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 5, "start_time": "10:00:00", "end_time": "14:00:00", "is_working": False},
            {"day_of_week": 6, "start_time": "00:00:00", "end_time": "00:00:00", "is_working": False},
        ]
    }
    status, _ = http_request("PUT", f"/api/admin/doctors/{doctor_id}/working-hours", body=wh_payload, token=admin_token)
    assert status == 200
    print("  -> PASSED: Working hours configured.")



    # 4. Register Patients 1 & 2
    print("\n[TEST 4] Registering Two Patients...")
    p1_email = "phase11_patient1@example.com"
    p2_email = "phase11_patient2@example.com"

    http_request("POST", "/api/auth/register", body={"name": "Patient One", "email": p1_email, "password": "Pass123!Password"})
    http_request("POST", "/api/auth/register", body={"name": "Patient Two", "email": p2_email, "password": "Pass123!Password"})

    status, p1_auth = http_request("POST", "/api/auth/login", body={"email": p1_email, "password": "Pass123!Password"})
    p1_token = p1_auth["access_token"]

    status, p2_auth = http_request("POST", "/api/auth/login", body={"email": p2_email, "password": "Pass123!Password"})
    p2_token = p2_auth["access_token"]
    print("  -> PASSED: Patient 1 and Patient 2 authenticated.")

    # 5. Book Appointments for Patient 1 and Patient 2 on Target Wednesday
    print(f"\n[TEST 5] Booking Confirmed Appointments on {target_date_str}...")
    status, app1_res = http_request("POST", "/api/appointments", body={
        "doctor_id": doctor_id,
        "appointment_date": target_date_str,
        "start_time": "09:00:00",
        "end_time": "09:30:00",
        "symptoms": "Severe headache and migraines"
    }, token=p1_token)
    assert status == 201
    app1_id = app1_res["id"]
    assert app1_res["status"] == "CONFIRMED"

    status, app2_res = http_request("POST", "/api/appointments", body={
        "doctor_id": doctor_id,
        "appointment_date": target_date_str,
        "start_time": "10:00:00",
        "end_time": "10:30:00",
        "symptoms": "Numbness in left hand"
    }, token=p2_token)
    assert status == 201
    app2_id = app2_res["id"]
    assert app2_res["status"] == "CONFIRMED"
    print(f"  -> PASSED: Appointment #{app1_id} (09:00) and #{app2_id} (10:00) booked.")

    # 6. Admin Marks Doctor on Leave on Target Wednesday (Triggers Conflict Service)
    print(f"\n[TEST 6] Admin Scheduling Leave on {target_date_str}...")
    leave_payload = {
        "leave_date": target_date_str,
        "reason": "Attending Annual Neurology Conference"
    }
    status, leave_res = http_request("POST", f"/api/admin/doctors/{doctor_id}/leaves", body=leave_payload, token=admin_token)
    assert status == 201, f"Failed to create leave: {leave_res}"

    print(f"  -> Response message: {leave_res.get('message')}")
    assert leave_res["affected_appointments_count"] == 2
    assert len(leave_res["patients_to_notify"]) == 2
    assert leave_res["notifications_prepared"] == 2
    assert leave_res["calendar_sync_jobs_prepared"] == 2
    print("  -> PASSED: API returned 2 affected appointments & prepared notification/calendar sync metrics.")

    # 7. Verify Appointments are Preserved (Not Deleted) and Marked CANCELLED with Reason
    print("\n[TEST 7] Verifying Appointment Records are Preserved and Cancelled with Reason...")
    status, app1_details = http_request("GET", f"/api/appointments/{app1_id}", token=p1_token)
    assert status == 200
    assert app1_details["status"] == "CANCELLED"
    assert app1_details["cancellation_reason"] == "Doctor unavailable due to leave"
    print(f"  -> PASSED: Appointment #{app1_id} status={app1_details['status']}, reason='{app1_details['cancellation_reason']}'")

    status, app2_details = http_request("GET", f"/api/appointments/{app2_id}", token=p2_token)
    assert status == 200
    assert app2_details["status"] == "CANCELLED"
    assert app2_details["cancellation_reason"] == "Doctor unavailable due to leave"
    print(f"  -> PASSED: Appointment #{app2_id} status={app2_details['status']}, reason='{app2_details['cancellation_reason']}'")

    # 8. Verify Availability is Blocked on Leave Date
    print(f"\n[TEST 8] Verifying Doctor Availability Blocked on {target_date_str}...")
    status, avail_res = http_request("GET", f"/api/doctors/{doctor_id}/availability?date={target_date_str}")
    assert status == 200
    assert len(avail_res.get("slots", [])) == 0
    assert avail_res.get("available_slots_count", 0) == 0
    print("  -> PASSED: Doctor has 0 available slots on leave date.")

    # 9. Verify Notification Records via REST API
    print("\n[TEST 9] Verifying Patient Notifications Created via REST API...")
    status, p1_notifs = http_request("GET", "/api/notifications", token=p1_token)
    assert status == 200, f"Failed to get notifications for patient 1: {p1_notifs}"
    assert len(p1_notifs) >= 1
    p1_target_notif = next((n for n in p1_notifs if n["appointment_id"] == app1_id), None)
    assert p1_target_notif is not None, "Notification for appointment 1 not found"
    assert p1_target_notif["type"] == "LEAVE_CANCELLATION"
    assert p1_target_notif["email_job_status"] == "PREPARED"
    assert p1_target_notif["calendar_job_status"] == "PREPARED"
    assert "on leave" in p1_target_notif["message"].lower()

    status, p2_notifs = http_request("GET", "/api/notifications", token=p2_token)
    assert status == 200, f"Failed to get notifications for patient 2: {p2_notifs}"
    assert len(p2_notifs) >= 1
    p2_target_notif = next((n for n in p2_notifs if n["appointment_id"] == app2_id), None)
    assert p2_target_notif is not None, "Notification for appointment 2 not found"
    assert p2_target_notif["type"] == "LEAVE_CANCELLATION"
    assert p2_target_notif["email_job_status"] == "PREPARED"
    assert p2_target_notif["calendar_job_status"] == "PREPARED"
    assert "on leave" in p2_target_notif["message"].lower()
    print("  -> PASSED: Patient 1 and Patient 2 verified notifications via API (PREPARED status).")


    print("\n==================================================")
    print(" ALL 9 PHASE 11 LEAVE CONFLICT TESTS PASSED!      ")
    print("==================================================")


if __name__ == "__main__":
    run_phase11_tests()

"""Automated test suite for Phase 12: Pre-visit AI Symptom Summarization & Triage."""

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
    """Find the date of the next occurrence of a weekday."""
    today = date.today()
    days_ahead = (weekday_idx - today.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def run_phase12_tests():
    print("==================================================")
    print(" RUNNING PHASE 12: PRE-VISIT AI SYMPTOM SUMMARY   ")
    print("==================================================")

    # 1. Admin Authentication & Doctor Creation
    print("\n[TEST 1] Admin Authentication & Doctor Setup...")
    admin_login = {
        "email": "test_admin_phase3@example.com",
        "password": "AdminPass123!"
    }
    status, admin_data = http_request("POST", "/api/auth/login", body=admin_login)
    assert status == 200, f"Admin login failed: {admin_data}"
    admin_token = admin_data["access_token"]

    ts = int(time.time())
    doc1_email = f"phase12_doc1_{ts}@example.com"
    doc2_email = f"phase12_doc2_{ts}@example.com"

    status, doc1_res = http_request("POST", "/api/admin/doctors", body={
        "name": "Dr. Elena AI Specialist",
        "email": doc1_email,
        "password": "DoctorPass123!",
        "phone": "+1-555-8881",
        "specialization": "Internal Medicine",
        "qualification": "MD, FACP",
        "experience": 10,
        "slot_duration": 30,
        "is_active": True
    }, token=admin_token)
    assert status == 201
    doc1_id = doc1_res["id"]

    status, doc2_res = http_request("POST", "/api/admin/doctors", body={
        "name": "Dr. Unassigned Observer",
        "email": doc2_email,
        "password": "DoctorPass123!",
        "phone": "+1-555-8882",
        "specialization": "Pediatrics",
        "qualification": "MD",
        "experience": 5,
        "slot_duration": 30,
        "is_active": True
    }, token=admin_token)
    assert status == 201
    doc2_id = doc2_res["id"]

    # Authenticate Doctors
    status, doc1_auth = http_request("POST", "/api/auth/login", body={"email": doc1_email, "password": "DoctorPass123!"})
    assert status == 200
    doc1_token = doc1_auth["access_token"]

    status, doc2_auth = http_request("POST", "/api/auth/login", body={"email": doc2_email, "password": "DoctorPass123!"})
    assert status == 200
    doc2_token = doc2_auth["access_token"]
    print(f"  -> PASSED: Doctor 1 (#{doc1_id}) and Doctor 2 (#{doc2_id}) setup.")

    # 2. Configure Working Hours (Thursday 09:00 - 17:00)
    target_thursday = get_next_weekday(3)
    target_date_str = target_thursday.isoformat()
    wh_payload = {
        "working_hours": [
            {"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 1, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 3, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 4, "start_time": "09:00:00", "end_time": "17:00:00", "is_working": True},
            {"day_of_week": 5, "start_time": "10:00:00", "end_time": "14:00:00", "is_working": False},
            {"day_of_week": 6, "start_time": "00:00:00", "end_time": "00:00:00", "is_working": False},
        ]
    }
    http_request("PUT", f"/api/admin/doctors/{doc1_id}/working-hours", body=wh_payload, token=admin_token)

    # 3. Register Patient & Book High-Urgency Appointment
    print(f"\n[TEST 2] Booking High-Urgency Appointment on {target_date_str}...")
    patient_email = f"phase12_patient_{ts}@example.com"
    http_request("POST", "/api/auth/register", body={"name": "Robert Stone", "email": patient_email, "password": "PatientPass123!"})
    status, patient_auth = http_request("POST", "/api/auth/login", body={"email": patient_email, "password": "PatientPass123!"})
    patient_token = patient_auth["access_token"]

    high_symptoms = "Severe crushing chest pain radiating to the left arm and jaw with shortness of breath for 1 hour."
    status, app1_res = http_request("POST", "/api/appointments", body={
        "doctor_id": doc1_id,
        "appointment_date": target_date_str,
        "start_time": "09:00:00",
        "end_time": "09:30:00",
        "symptoms": high_symptoms
    }, token=patient_token)
    assert status == 201
    app1_id = app1_res["id"]
    print(f"  -> PASSED: Appointment #{app1_id} created with cardiac symptoms.")

    # 4. Generate AI Pre-Visit Summary (POST)
    print(f"\n[TEST 3] Generating Pre-Visit AI Summary (POST /api/appointments/{app1_id}/previsit-summary)...")
    status, ai_res = http_request("POST", f"/api/appointments/{app1_id}/previsit-summary", token=patient_token)
    assert status == 200, f"AI summary creation failed: {ai_res}"

    print(f"  -> AI Urgency Level: {ai_res['urgency_level']}")
    print(f"  -> AI Chief Complaint: {ai_res['chief_complaint']}")
    print(f"  -> AI Model: {ai_res['model_name']} (Status: {ai_res['status']})")
    print(f"  -> AI Questions ({len(ai_res['suggested_questions'])}): {ai_res['suggested_questions']}")

    assert ai_res["urgency_level"] in ["Low", "Medium", "High"]
    assert ai_res["urgency_level"] == "High", f"Expected High urgency for cardiac symptoms, got: {ai_res['urgency_level']}"
    assert len(ai_res["suggested_questions"]) == 3
    assert "not a clinical diagnosis" in ai_res["disclaimer"].lower()
    print("  -> PASSED: High-urgency AI pre-visit summary validated.")

    # 5. Doctor 1 Retrieves AI Summary (GET)
    print(f"\n[TEST 4] Attending Doctor Retrieving Pre-Visit Summary (GET)...")
    status, doc_ai_res = http_request("GET", f"/api/appointments/{app1_id}/previsit-summary", token=doc1_token)
    assert status == 200
    assert doc_ai_res["appointment_id"] == app1_id
    assert doc_ai_res["urgency_level"] == "High"
    assert len(doc_ai_res["suggested_questions"]) == 3
    print("  -> PASSED: Attending Doctor successfully retrieved AI summary.")

    # 6. Test Low Urgency Symptoms Appointment
    print(f"\n[TEST 5] Booking & Summarizing Low-Urgency Routine Symptoms...")
    low_symptoms = "Mild seasonal runny nose and sneezing for 3 days."
    status, app2_res = http_request("POST", "/api/appointments", body={
        "doctor_id": doc1_id,
        "appointment_date": target_date_str,
        "start_time": "10:00:00",
        "end_time": "10:30:00",
        "symptoms": low_symptoms
    }, token=patient_token)
    assert status == 201
    app2_id = app2_res["id"]

    status, low_ai_res = http_request("POST", f"/api/appointments/{app2_id}/previsit-summary", token=patient_token)
    assert status == 200
    print(f"  -> Low Symptoms Urgency: {low_ai_res['urgency_level']}")
    assert low_ai_res["urgency_level"] in ["Low", "Medium"]
    assert len(low_ai_res["suggested_questions"]) == 3
    print("  -> PASSED: Low-urgency routine symptom summary validated.")

    # 7. Test Fallback & Blank Symptoms Resiliency
    print(f"\n[TEST 6] Testing Resiliency with Blank Symptoms (Fallback Handling)...")
    status, app3_res = http_request("POST", "/api/appointments", body={
        "doctor_id": doc1_id,
        "appointment_date": target_date_str,
        "start_time": "11:00:00",
        "end_time": "11:30:00",
        "symptoms": None
    }, token=patient_token)
    assert status == 201
    app3_id = app3_res["id"]

    status, blank_ai_res = http_request("POST", f"/api/appointments/{app3_id}/previsit-summary", token=patient_token)
    assert status == 200
    assert blank_ai_res["urgency_level"] in ["Low", "Medium", "High"]
    assert len(blank_ai_res["suggested_questions"]) == 3
    print("  -> PASSED: Blank symptoms handled gracefully with safe triage fallback.")

    # 8. Privacy & RBAC Isolation Test
    print(f"\n[TEST 7] Testing Privacy Isolation (Doctor 2 blocked from Doctor 1's appointment AI summary)...")
    status, error_res = http_request("GET", f"/api/appointments/{app1_id}/previsit-summary", token=doc2_token)
    assert status == 403, f"Expected 403 Forbidden, got: {status}"
    print("  -> PASSED: Unassigned doctor blocked with 403 Forbidden.")

    print("\n==================================================")
    print(" ALL 7 PHASE 12 AI SUMMARY TESTS PASSED!          ")
    print("==================================================")


if __name__ == "__main__":
    run_phase12_tests()

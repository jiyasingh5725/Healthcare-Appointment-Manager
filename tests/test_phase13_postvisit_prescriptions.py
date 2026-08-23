"""
Automated Test Suite for Phase 13: Doctor Post-Visit Consultations & Prescriptions.
"""

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
    today = date.today()
    days_ahead = (weekday_idx - today.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def run_phase13_tests():
    print("==========================================================")
    print(" RUNNING PHASE 13: POST-VISIT CONSULTATIONS & PRESCRIPTIONS ")
    print("==========================================================")

    ts = int(time.time())

    # 1. Login as Admin
    print("\n[TEST 1] Admin Authentication...")
    admin_login = {
        "email": "test_admin_phase3@example.com",
        "password": "AdminPass123!"
    }
    status, admin_data = http_request("POST", "/api/auth/login", body=admin_login)
    assert status == 200, f"Admin login failed: {admin_data}"
    admin_token = admin_data["access_token"]
    print("-> Admin authenticated.")

    # 2. Create Attending Doctor A & Unrelated Doctor B
    print("\n[TEST 2] Provisioning Doctors A & B...")
    doc1_payload = {
        "name": f"Dr. House {ts}",
        "email": f"house_{ts}@example.com",
        "password": "DoctorPass123!",
        "specialization": "Diagnostics",
        "experience_years": 15,
        "consultation_fee": 300.0,
        "is_active": True
    }
    status, doc1_res = http_request("POST", "/api/admin/doctors", body=doc1_payload, token=admin_token)
    assert status == 201, f"Doctor A creation failed: {doc1_res}"
    doc1_id = doc1_res["id"]

    doc2_payload = {
        "name": f"Dr. Wilson {ts}",
        "email": f"wilson_{ts}@example.com",
        "password": "DoctorPass123!",
        "specialization": "Oncology",
        "experience_years": 12,
        "consultation_fee": 250.0,
        "is_active": True
    }
    status, doc2_res = http_request("POST", "/api/admin/doctors", body=doc2_payload, token=admin_token)
    assert status == 201, f"Doctor B creation failed: {doc2_res}"
    doc2_id = doc2_res["id"]

    # Doctor working hours for Monday (0)
    wh_payload = {
        "working_hours": [
            {"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00", "slot_duration": 30, "is_active": True}
        ]
    }
    s1, r1 = http_request("PUT", f"/api/admin/doctors/{doc1_id}/working-hours", body=wh_payload, token=admin_token)
    assert s1 == 200, f"Doctor A working hours failed: {r1}"
    s2, r2 = http_request("PUT", f"/api/admin/doctors/{doc2_id}/working-hours", body=wh_payload, token=admin_token)
    assert s2 == 200, f"Doctor B working hours failed: {r2}"


    # Doctor Login Tokens
    _, doc1_auth = http_request("POST", "/api/auth/login", body={"email": doc1_payload["email"], "password": doc1_payload["password"]})
    doc1_token = doc1_auth["access_token"]

    _, doc2_auth = http_request("POST", "/api/auth/login", body={"email": doc2_payload["email"], "password": doc2_payload["password"]})
    doc2_token = doc2_auth["access_token"]
    print("-> Doctors provisioned and authenticated.")

    # 3. Create Patient 1 and Patient 2
    print("\n[TEST 3] Registering Patients...")
    pat1_payload = {
        "name": f"Patient Alpha {ts}",
        "email": f"pat1_{ts}@example.com",
        "password": "PatientPass123!",
        "phone": "+1234567890"
    }
    status, pat1_res = http_request("POST", "/api/auth/register", body=pat1_payload)
    assert status == 201, f"Patient 1 registration failed: {pat1_res}"

    _, pat1_auth = http_request("POST", "/api/auth/login", body={"email": pat1_payload["email"], "password": pat1_payload["password"]})
    pat1_token = pat1_auth["access_token"]

    pat2_payload = {
        "name": f"Patient Beta {ts}",
        "email": f"pat2_{ts}@example.com",
        "password": "PatientPass123!",
        "phone": "+1987654321"
    }
    status, pat2_res = http_request("POST", "/api/auth/register", body=pat2_payload)
    assert status == 201, f"Patient 2 registration failed: {pat2_res}"

    _, pat2_auth = http_request("POST", "/api/auth/login", body={"email": pat2_payload["email"], "password": pat2_payload["password"]})
    pat2_token = pat2_auth["access_token"]
    print("-> Patients registered and authenticated.")

    # 4. Book Appointment with Doctor A for Patient 1
    print("\n[TEST 4] Booking Confirmed Appointment...")
    target_date = get_next_weekday(0).isoformat()
    app_payload = {
        "doctor_id": doc1_id,
        "appointment_date": target_date,
        "start_time": "10:00:00",
        "end_time": "10:30:00",
        "symptoms": "Persistent dry cough, mild fever 101F, chest tightness for 3 days."
    }
    status, app_res = http_request("POST", "/api/appointments", body=app_payload, token=pat1_token)
    assert status == 201, f"Appointment creation failed: {app_res}"
    appointment_id = app_res["id"]
    print(f"-> Appointment #{appointment_id} booked with Dr. {doc1_payload['name']}.")

    # 5. RBAC Violation: Unauthorized Doctor B tries to submit consultation
    print("\n[TEST 5] Testing RBAC Security: Doctor B submitting on Doctor A's appointment...")
    status, res_unauth_doc = http_request(
        "POST",
        f"/api/appointments/{appointment_id}/consultation",
        body={"notes": "Unauthorized notes", "follow_up_instructions": "None"},
        token=doc2_token
    )
    assert status == 403, f"Expected 403 Forbidden for Doctor B, got {status}: {res_unauth_doc}"
    print("-> Doctor B 403 Forbidden verified.")

    # 6. RBAC Violation: Patient tries to submit consultation
    print("\n[TEST 6] Testing RBAC Security: Patient submitting consultation...")
    status, res_unauth_pat = http_request(
        "POST",
        f"/api/appointments/{appointment_id}/consultation",
        body={"notes": "Patient notes"},
        token=pat1_token
    )
    assert status == 403, f"Expected 403 Forbidden for Patient, got {status}: {res_unauth_pat}"
    print("-> Patient 403 Forbidden verified.")

    # 7. Doctor A Submits Consultation Clinical Notes
    print("\n[TEST 7] Attending Doctor A submits consultation notes...")
    consultation_payload = {
        "notes": "Patient presents with acute viral bronchitis. Mild expiratory wheeze. Temp 100.8F. SpO2 98%.",
        "follow_up_instructions": "Review in 5 days if cough or fever persists. Keep well hydrated."
    }
    status, consult_res = http_request(
        "POST",
        f"/api/appointments/{appointment_id}/consultation",
        body=consultation_payload,
        token=doc1_token
    )
    assert status == 200, f"Consultation submission failed: {consult_res}"
    assert consult_res["appointment_id"] == appointment_id
    assert consult_res["doctor_name"] == doc1_payload["name"]
    assert "acute viral bronchitis" in consult_res["notes"]
    print("-> Consultation submitted successfully.")

    # Verify Appointment Status became COMPLETED
    status, app_check = http_request("GET", f"/api/appointments/{appointment_id}", token=doc1_token)
    assert status == 200
    assert app_check["status"] == "COMPLETED", f"Expected COMPLETED status, got {app_check['status']}"
    print("-> Appointment transitioned to COMPLETED.")

    # 8. Doctor A Issues Clinical Prescription with Medications
    print("\n[TEST 8] Doctor A issues full prescription with medications...")
    prescription_payload = {
        "notes": "Acute viral bronchitis with secondary bacterial infection suspected.",
        "follow_up_instructions": "Hydration, vocal rest, and 7-day post-antibiotic review.",
        "medications": [
            {
                "medication_name": "Azithromycin 500mg",
                "dosage": "1 tablet",
                "frequency": "Once daily after meals",
                "duration": "3 days",
                "instructions": "Take at the same time each day with plenty of water",
                "reminder_enabled": True
            },
            {
                "medication_name": "Dextromethorphan Cough Syrup",
                "dosage": "10ml",
                "frequency": "Three times daily",
                "duration": "5 days",
                "instructions": "Take after meals and before bed",
                "reminder_enabled": True
            },
            {
                "medication_name": "Paracetamol 650mg",
                "dosage": "1 tablet",
                "frequency": "As needed (SOS) max 3/day",
                "duration": "3 days",
                "instructions": "For fever above 100F",
                "reminder_enabled": False
            }
        ]
    }
    status, rx_res = http_request(
        "POST",
        f"/api/appointments/{appointment_id}/prescription",
        body=prescription_payload,
        token=doc1_token
    )
    assert status == 200, f"Prescription submission failed: {rx_res}"
    assert rx_res["appointment_id"] == appointment_id
    assert len(rx_res["medications"]) == 3
    assert rx_res["medications"][0]["medication_name"] == "Azithromycin 500mg"
    assert rx_res["medications"][1]["dosage"] == "10ml"
    assert rx_res["medications"][2]["reminder_enabled"] is False
    print("-> Clinical prescription with 3 medications issued successfully.")

    # 9. Patient 1 Fetches Their Prescription
    print("\n[TEST 9] Patient 1 retrieves their prescription...")
    status, pat1_rx_res = http_request(
        "GET",
        f"/api/appointments/{appointment_id}/prescription",
        token=pat1_token
    )
    assert status == 200, f"Patient prescription retrieval failed: {pat1_rx_res}"
    assert pat1_rx_res["patient_name"] == pat1_payload["name"]
    assert len(pat1_rx_res["medications"]) == 3
    print("-> Patient successfully accessed prescription.")

    # 10. Doctor A Fetches The Prescription
    print("\n[TEST 10] Doctor A retrieves prescription...")
    status, doc_rx_res = http_request(
        "GET",
        f"/api/appointments/{appointment_id}/prescription",
        token=doc1_token
    )
    assert status == 200, f"Doctor prescription retrieval failed: {doc_rx_res}"
    assert len(doc_rx_res["medications"]) == 3
    print("-> Doctor successfully accessed prescription.")

    # 11. RBAC Violation: Patient 2 (Unauthorized) attempts to fetch Patient 1's prescription
    print("\n[TEST 11] Testing RBAC Security: Patient 2 accessing Patient 1's prescription...")
    status, pat2_rx_res = http_request(
        "GET",
        f"/api/appointments/{appointment_id}/prescription",
        token=pat2_token
    )
    assert status == 403, f"Expected 403 Forbidden for Patient 2, got {status}: {pat2_rx_res}"
    print("-> Patient 2 403 Forbidden verified.")

    # 12. RBAC Violation: Doctor B (Unauthorized) attempts to fetch Patient 1's prescription
    print("\n[TEST 12] Testing RBAC Security: Doctor B accessing Patient 1's prescription...")
    status, doc2_rx_res = http_request(
        "GET",
        f"/api/appointments/{appointment_id}/prescription",
        token=doc2_token
    )
    assert status == 403, f"Expected 403 Forbidden for Doctor B, got {status}: {doc2_rx_res}"
    print("-> Doctor B 403 Forbidden verified.")

    # 13. Input Validation: Empty medication name / dosage rejection
    print("\n[TEST 13] Testing Input Validation on invalid medication item...")
    invalid_payload = {
        "notes": "Valid notes",
        "medications": [
            {
                "medication_name": "",  # Empty name should fail min_length=1
                "dosage": "500mg",
                "frequency": "Daily",
                "duration": "5 days"
            }
        ]
    }
    status, val_res = http_request(
        "POST",
        f"/api/appointments/{appointment_id}/prescription",
        body=invalid_payload,
        token=doc1_token
    )
    assert status == 422, f"Expected 422 Unprocessable Entity for empty medication name, got {status}: {val_res}"
    print("-> 422 validation rejection verified.")

    print("\n==========================================================")
    print(" ALL 13 PHASE 13 TESTS PASSED SUCCESSFULLY!               ")
    print("==========================================================")


if __name__ == "__main__":
    run_phase13_tests()

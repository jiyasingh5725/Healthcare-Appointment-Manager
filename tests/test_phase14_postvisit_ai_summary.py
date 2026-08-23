"""
Automated Test Suite for Phase 14: Patient-Friendly Post-Visit AI Care Summary.
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


def run_phase14_tests():
    print("================================================================")
    print(" RUNNING PHASE 14: PATIENT-FRIENDLY POST-VISIT AI CARE SUMMARY  ")
    print("================================================================")

    ts = int(time.time())

    # 1. Admin Authentication
    print("\n[TEST 1] Admin Authentication...")
    admin_login = {
        "email": "test_admin_phase3@example.com",
        "password": "AdminPass123!"
    }
    status, admin_data = http_request("POST", "/api/auth/login", body=admin_login)
    assert status == 200, f"Admin login failed: {admin_data}"
    admin_token = admin_data["access_token"]
    print("-> PASSED: Admin authenticated.")

    # 2. Provisioning Attending Doctor 1 & Doctor 2
    print("\n[TEST 2] Provisioning Attending Doctors...")
    doc1_payload = {
        "name": f"Dr. Meredith Grey {ts}",
        "email": f"grey_{ts}@example.com",
        "password": "DoctorPass123!",
        "specialization": "General Surgery & Medicine",
        "experience_years": 10,
        "consultation_fee": 220.0,
        "is_active": True
    }
    status, doc1_res = http_request("POST", "/api/admin/doctors", body=doc1_payload, token=admin_token)
    assert status == 201, f"Doctor 1 creation failed: {doc1_res}"
    doc1_id = doc1_res["id"]

    doc2_payload = {
        "name": f"Dr. Derek Shepherd {ts}",
        "email": f"shepherd_{ts}@example.com",
        "password": "DoctorPass123!",
        "specialization": "Neurosurgery",
        "experience_years": 14,
        "consultation_fee": 350.0,
        "is_active": True
    }
    status, doc2_res = http_request("POST", "/api/admin/doctors", body=doc2_payload, token=admin_token)
    assert status == 201, f"Doctor 2 creation failed: {doc2_res}"
    doc2_id = doc2_res["id"]

    # Configure working hours for Tuesday (1)
    wh_payload = {
        "working_hours": [
            {"day_of_week": 1, "start_time": "09:00:00", "end_time": "17:00:00", "slot_duration": 30, "is_active": True}
        ]
    }
    http_request("PUT", f"/api/admin/doctors/{doc1_id}/working-hours", body=wh_payload, token=admin_token)
    http_request("PUT", f"/api/admin/doctors/{doc2_id}/working-hours", body=wh_payload, token=admin_token)

    _, doc1_auth = http_request("POST", "/api/auth/login", body={"email": doc1_payload["email"], "password": doc1_payload["password"]})
    doc1_token = doc1_auth["access_token"]

    _, doc2_auth = http_request("POST", "/api/auth/login", body={"email": doc2_payload["email"], "password": doc2_payload["password"]})
    doc2_token = doc2_auth["access_token"]
    print("-> PASSED: Doctors provisioned.")

    # 3. Register Patient 1 & Patient 2
    print("\n[TEST 3] Registering Patient 1 & Patient 2...")
    pat1_payload = {
        "name": f"Alice Johnson {ts}",
        "email": f"alice_{ts}@example.com",
        "password": "PatientPass123!",
        "phone": "+15551234567"
    }
    status, pat1_res = http_request("POST", "/api/auth/register", body=pat1_payload)
    assert status == 201, f"Patient 1 registration failed: {pat1_res}"

    _, pat1_auth = http_request("POST", "/api/auth/login", body={"email": pat1_payload["email"], "password": pat1_payload["password"]})
    pat1_token = pat1_auth["access_token"]

    pat2_payload = {
        "name": f"Bob Miller {ts}",
        "email": f"bob_{ts}@example.com",
        "password": "PatientPass123!",
        "phone": "+15559876543"
    }
    status, pat2_res = http_request("POST", "/api/auth/register", body=pat2_payload)
    assert status == 201, f"Patient 2 registration failed: {pat2_res}"

    _, pat2_auth = http_request("POST", "/api/auth/login", body={"email": pat2_payload["email"], "password": pat2_payload["password"]})
    pat2_token = pat2_auth["access_token"]
    print("-> PASSED: Patients registered.")

    # 4. Book Confirmed Appointment
    print("\n[TEST 4] Booking Confirmed Appointment...")
    target_date = get_next_weekday(1).isoformat()
    app_payload = {
        "doctor_id": doc1_id,
        "appointment_date": target_date,
        "start_time": "11:00:00",
        "end_time": "11:30:00",
        "symptoms": "Severe sinus headache, facial pressure, yellow-green nasal discharge for 5 days."
    }
    status, app_res = http_request("POST", "/api/appointments", body=app_payload, token=pat1_token)
    assert status == 201, f"Appointment booking failed: {app_res}"
    appointment_id = app_res["id"]
    print(f"-> PASSED: Appointment #{appointment_id} booked.")

    # 5. Doctor Submits Post-Visit Consultation & Prescription
    print("\n[TEST 5] Doctor Submits Clinical Prescription...")
    prescription_payload = {
        "notes": "Patient diagnosed with Acute Bacterial Sinusitis. Bilateral maxillary sinus tenderness noted on palpation. Mild pharyngeal erythema. Lungs clear to auscultation.",
        "follow_up_instructions": "Complete full antibiotic course. Perform warm saline nasal irrigation twice daily. Review in 7 days if sinus pain persists.",
        "medications": [
            {
                "medication_name": "Amoxicillin-Clavulanate 625mg",
                "dosage": "1 tablet",
                "frequency": "Twice daily after meals",
                "duration": "7 days",
                "instructions": "Do not skip doses. Take with food to avoid stomach upset.",
                "reminder_enabled": True
            },
            {
                "medication_name": "Oxymetazoline 0.05% Nasal Spray",
                "dosage": "2 sprays per nostril",
                "frequency": "Twice daily",
                "duration": "3 days max",
                "instructions": "Do not use for more than 3 consecutive days to prevent rebound congestion.",
                "reminder_enabled": True
            },
            {
                "medication_name": "Paracetamol 650mg",
                "dosage": "1 tablet",
                "frequency": "Every 6-8 hours as needed",
                "duration": "5 days",
                "instructions": "For facial headache and sinus pressure",
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
    print("-> PASSED: Clinical consultation and prescription saved. Status is COMPLETED.")

    # 6. Generate Patient-Friendly Post-Visit AI Summary (POST)
    print("\n[TEST 6] Generating Patient-Friendly Post-Visit AI Summary (POST /postvisit-summary)...")
    status, ai_res = http_request(
        "POST",
        f"/api/appointments/{appointment_id}/postvisit-summary",
        token=pat1_token
    )
    assert status == 200, f"Post-visit AI summary generation failed: {ai_res}"
    assert ai_res["summary_type"] == "POST_VISIT", f"Expected summary_type POST_VISIT, got {ai_res.get('summary_type')}"
    assert "summary" in ai_res and len(ai_res["summary"]) > 10, "Summary text missing or too short"
    assert "medication_schedule" in ai_res and isinstance(ai_res["medication_schedule"], list), "Medication schedule missing"
    assert len(ai_res["medication_schedule"]) == 3, f"Expected 3 medications in schedule, got {len(ai_res['medication_schedule'])}"
    assert "follow_up_steps" in ai_res and isinstance(ai_res["follow_up_steps"], list), "Follow up steps missing"
    assert len(ai_res["follow_up_steps"]) >= 1, "Expected at least 1 follow up step"
    assert "disclaimer" in ai_res, "Disclaimer missing"
    assert ai_res["status"] in ["SUCCESS", "FALLBACK"], f"Unexpected status: {ai_res['status']}"

    print(f"  -> Generated Summary: {ai_res['summary'][:120]}...")
    print(f"  -> Medication Schedule Count: {len(ai_res['medication_schedule'])}")
    print(f"  -> Follow-up Steps: {ai_res['follow_up_steps']}")
    print(f"  -> Model: {ai_res['model_name']} [{ai_res['status']}]")
    print("-> PASSED: Patient-friendly post-visit summary verified.")

    # 7. Fetch Post-Visit AI Summary as Patient 1 (GET)
    print("\n[TEST 7] Patient 1 Retrieving Post-Visit AI Summary (GET)...")
    status, get_pat1 = http_request(
        "GET",
        f"/api/appointments/{appointment_id}/postvisit-summary",
        token=pat1_token
    )
    assert status == 200, f"Patient GET failed: {get_pat1}"
    assert get_pat1["summary_type"] == "POST_VISIT"
    assert len(get_pat1["medication_schedule"]) == 3
    print("-> PASSED: Patient retrieved post-visit summary.")

    # 8. Fetch Post-Visit AI Summary as Attending Doctor 1 (GET)
    print("\n[TEST 8] Attending Doctor 1 Retrieving Post-Visit AI Summary (GET)...")
    status, get_doc1 = http_request(
        "GET",
        f"/api/appointments/{appointment_id}/postvisit-summary",
        token=doc1_token
    )
    assert status == 200, f"Doctor GET failed: {get_doc1}"
    assert get_doc1["summary_type"] == "POST_VISIT"
    print("-> PASSED: Attending Doctor retrieved post-visit summary.")

    # 9. RBAC Violation: Unauthorized Patient 2 accessing summary
    print("\n[TEST 9] RBAC Security: Unauthorized Patient 2 accessing summary...")
    status, res_pat2 = http_request(
        "GET",
        f"/api/appointments/{appointment_id}/postvisit-summary",
        token=pat2_token
    )
    assert status == 403, f"Expected 403 Forbidden for Patient 2, got {status}: {res_pat2}"
    print("-> PASSED: Patient 2 blocked with 403 Forbidden.")

    # 10. RBAC Violation: Unauthorized Doctor 2 accessing summary
    print("\n[TEST 10] RBAC Security: Unauthorized Doctor 2 accessing summary...")
    status, res_doc2 = http_request(
        "GET",
        f"/api/appointments/{appointment_id}/postvisit-summary",
        token=doc2_token
    )
    assert status == 403, f"Expected 403 Forbidden for Doctor 2, got {status}: {res_doc2}"
    print("-> PASSED: Doctor 2 blocked with 403 Forbidden.")

    # 11. Preserving Original Clinical Records
    print("\n[TEST 11] Verifying Original Physician Clinical Notes & Prescriptions...")
    status, rx_check = http_request(
        "GET",
        f"/api/appointments/{appointment_id}/prescription",
        token=pat1_token
    )
    assert status == 200
    assert "Acute Bacterial Sinusitis" in rx_check["notes"], "Original notes were modified!"
    assert len(rx_check["medications"]) == 3
    assert rx_check["medications"][0]["medication_name"] == "Amoxicillin-Clavulanate 625mg"
    print("-> PASSED: Original physician clinical notes and prescriptions remain 100% pristine.")

    print("\n================================================================")
    print(" ALL 11 PHASE 14 POST-VISIT AI SUMMARY TESTS PASSED!            ")
    print("================================================================")


if __name__ == "__main__":
    run_phase14_tests()

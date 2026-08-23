"""Automated test suite for Phase 4: Complete Admin Doctor Management."""

import urllib.request
import urllib.error
import json

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


def run_phase4_tests():
    print("==================================================")
    print("  RUNNING PHASE 4: ADMIN DOCTOR MANAGEMENT TESTS  ")
    print("==================================================")

    # 1. Admin Login
    print("\n[TEST 1] Authenticating Admin User...")
    admin_login = {
        "email": "test_admin_phase3@example.com",
        "password": "AdminPass123!"
    }
    status, data = http_request("POST", "/api/auth/login", body=admin_login)
    assert status == 200, f"Admin login failed with status {status}: {data}"
    admin_token = data["access_token"]
    print("  -> PASSED: Admin authenticated successfully.")

    # 2. Patient Registration / Login (to test RBAC protection)
    print("\n[TEST 2] Ensuring Patient User exists for RBAC check...")
    patient_body = {
        "name": "Jane Patient",
        "email": "test_patient_phase4@example.com",
        "password": "PatientPassword123!",
        "phone": "+1-555-0199"
    }
    http_request("POST", "/api/auth/register", body=patient_body)
    
    patient_login = {
        "email": "test_patient_phase4@example.com",
        "password": "PatientPassword123!"
    }
    status, data = http_request("POST", "/api/auth/login", body=patient_login)
    assert status == 200, f"Patient login failed with status {status}: {data}"
    patient_token = data["access_token"]
    print("  -> PASSED: Patient authenticated.")

    # 3. Patient / Unauthenticated Attempt to Create Doctor (Expecting 403 / 401)
    print("\n[TEST 3] Verifying Security: Non-Admin Cannot Create Doctors...")
    doc_payload = {
        "name": "Dr. Gregory House",
        "email": "dr.house.phase4@hospital.org",
        "password": "HousePassword123!",
        "phone": "+1-555-8888",
        "specialization": "Diagnostic Medicine",
        "qualification": "MD, Nephrology & Infectious Disease",
        "experience": 20,
        "slot_duration": 45,
        "is_active": True
    }
    # Unauthenticated -> 401
    status, data = http_request("POST", "/api/admin/doctors", body=doc_payload)
    assert status == 401, f"Expected 401 for unauthenticated request, got {status}"

    # Patient -> 403
    status, data = http_request("POST", "/api/admin/doctors", body=doc_payload, token=patient_token)
    assert status == 403, f"Expected 403 Forbidden for patient token, got {status}"
    print("  -> PASSED: Creation blocked with 401 for anonymous and 403 for patients.")

    # 4. Admin Creates Doctor (Success 201)
    print("\n[TEST 4] Admin Creating Doctor (Atomic User + Doctor Transaction)...")
    status, data = http_request("POST", "/api/admin/doctors", body=doc_payload, token=admin_token)
    assert status == 201, f"Expected 201 Created, got {status}: {data}"
    assert data["name"] == "Dr. Gregory House"
    assert data["specialization"] == "Diagnostic Medicine"
    assert data["slot_duration"] == 45
    assert data["experience"] == 20
    assert data["is_active"] is True
    created_doc_id = data["id"]
    print(f"  -> PASSED: Doctor created with ID #{created_doc_id}, User ID #{data['user_id']}.")

    # 5. Duplicate Email Validation (409 Conflict)
    print("\n[TEST 5] Duplicate Email Validation on Doctor Creation (Expecting 409)...")
    status, data = http_request("POST", "/api/admin/doctors", body=doc_payload, token=admin_token)
    assert status == 409, f"Expected 409 Conflict for duplicate email, got {status}: {data}"
    print("  -> PASSED: Duplicate doctor email rejected with 409 Conflict.")

    # 6. Invalid Slot Duration Validation (< 10 or > 120)
    print("\n[TEST 6] Invalid Slot Duration Validation (Expecting 422 or 400)...")
    bad_slot_payload = doc_payload.copy()
    bad_slot_payload["email"] = "dr.badslot@hospital.org"
    bad_slot_payload["slot_duration"] = 5  # Too short (< 10)
    status, data = http_request("POST", "/api/admin/doctors", body=bad_slot_payload, token=admin_token)
    assert status in (400, 422), f"Expected 400/422 for invalid slot duration, got {status}: {data}"
    print("  -> PASSED: Invalid slot duration rejected.")

    # 7. Public GET /api/doctors and GET /api/doctors/{id}
    print("\n[TEST 7] Public GET /api/doctors and GET /api/doctors/{id}...")
    status, doctors_list = http_request("GET", "/api/doctors?active_only=false")
    assert status == 200, f"Failed to list doctors: {status}"
    assert any(d["id"] == created_doc_id for d in doctors_list), "Created doctor not in list!"

    status, single_doc = http_request("GET", f"/api/doctors/{created_doc_id}")
    assert status == 200, f"Failed to fetch doctor by ID: {status}"
    assert single_doc["id"] == created_doc_id
    assert single_doc["specialization"] == "Diagnostic Medicine"
    print(f"  -> PASSED: Doctor retrieved via public API.")

    # 8. Admin Updates Doctor Profile (PUT)
    print("\n[TEST 8] Admin Updating Doctor Profile (PUT /api/admin/doctors/{id})...")
    update_payload = {
        "name": "Dr. Gregory House, MD",
        "phone": "+1-555-9999",
        "specialization": "Diagnostic & Internal Medicine",
        "qualification": "MD, FACP, Nephrology",
        "experience": 22,
        "slot_duration": 60,
        "is_active": True
    }
    status, data = http_request("PUT", f"/api/admin/doctors/{created_doc_id}", body=update_payload, token=admin_token)
    assert status == 200, f"Update failed with status {status}: {data}"
    assert data["name"] == "Dr. Gregory House, MD"
    assert data["phone"] == "+1-555-9999"
    assert data["specialization"] == "Diagnostic & Internal Medicine"
    assert data["slot_duration"] == 60
    assert data["experience"] == 22
    print("  -> PASSED: Doctor details updated successfully.")

    # 9. Admin Deactivates Doctor (PATCH)
    print("\n[TEST 9] Admin Deactivating Doctor (PATCH /api/admin/doctors/{id}/status)...")
    status_payload = {"is_active": False}
    status, data = http_request("PATCH", f"/api/admin/doctors/{created_doc_id}/status", body=status_payload, token=admin_token)
    assert status == 200, f"Status update failed: {status}: {data}"
    assert data["is_active"] is False

    # Check active_only query excludes deactivated doctor
    status, active_list = http_request("GET", "/api/doctors?active_only=true")
    assert not any(d["id"] == created_doc_id for d in active_list), "Deactivated doctor appeared in active list!"
    print("  -> PASSED: Doctor deactivated and excluded from active directory.")

    # 10. Admin Re-activates Doctor (PATCH)
    print("\n[TEST 10] Admin Re-activating Doctor...")
    status_payload = {"is_active": True}
    status, data = http_request("PATCH", f"/api/admin/doctors/{created_doc_id}/status", body=status_payload, token=admin_token)
    assert status == 200, f"Status update failed: {status}: {data}"
    assert data["is_active"] is True
    print("  -> PASSED: Doctor re-activated successfully.")

    print("\n==================================================")
    print("  ALL 10 PHASE 4 ADMIN DOCTOR TESTS PASSED!       ")
    print("==================================================")


if __name__ == "__main__":
    run_phase4_tests()

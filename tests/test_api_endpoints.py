"""Live HTTP API endpoint test suite for Phase 3."""

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


def run_api_tests():
    print("==================================================")
    print("   RUNNING LIVE HTTP AUTH & RBAC API TESTS        ")
    print("==================================================")

    # 1. Patient Registration
    print("\n[TEST 1] Registering a new Patient...")
    reg_body = {
        "name": "Jane Doe",
        "email": "test_patient_phase3@example.com",
        "password": "PatientPassword123!",
        "phone": "+1-555-0199"
    }
    status, data = http_request("POST", "/api/auth/register", body=reg_body)
    assert status == 201, f"Expected 201 Created, got {status}: {data}"
    assert data["role"] == "PATIENT", f"Expected PATIENT role, got {data.get('role')}"
    assert "password_hash" not in data, "Password hash leaked in response!"
    print(f"  -> PASSED: Patient registered with ID #{data['id']}, role={data['role']}")

    # 2. Duplicate Email Registration (409 Conflict)
    print("\n[TEST 2] Duplicate Email Registration (Expecting 409)...")
    status, data = http_request("POST", "/api/auth/register", body=reg_body)
    assert status == 409, f"Expected 409 Conflict, got {status}: {data}"
    print(f"  -> PASSED: Rejected duplicate email with 409 Conflict.")

    # 3. Patient Login (Valid)
    print("\n[TEST 3] Patient Login with Valid Credentials...")
    login_body = {
        "email": "test_patient_phase3@example.com",
        "password": "PatientPassword123!"
    }
    status, data = http_request("POST", "/api/auth/login", body=login_body)
    assert status == 200, f"Expected 200 OK, got {status}: {data}"
    assert "access_token" in data, "Access token missing in login response!"
    assert data["user"]["role"] == "PATIENT", f"Expected PATIENT role, got {data['user']['role']}"
    patient_token = data["access_token"]
    print(f"  -> PASSED: Patient logged in successfully. JWT Token received.")

    # 4. Login with Invalid Password (401 Unauthorized)
    print("\n[TEST 4] Login with Invalid Password (Expecting 401)...")
    bad_login = {
        "email": "test_patient_phase3@example.com",
        "password": "WrongPassword999"
    }
    status, data = http_request("POST", "/api/auth/login", body=bad_login)
    assert status == 401, f"Expected 401 Unauthorized, got {status}: {data}"
    print(f"  -> PASSED: Rejected invalid credentials with 401 Unauthorized.")

    # 5. Inactive User Login (403 Forbidden)
    print("\n[TEST 5] Inactive User Login (Expecting 403)...")
    inactive_login = {
        "email": "test_inactive_phase3@example.com",
        "password": "InactivePass123!"
    }
    status, data = http_request("POST", "/api/auth/login", body=inactive_login)
    assert status == 403, f"Expected 403 Forbidden, got {status}: {data}"
    print(f"  -> PASSED: Inactive account rejected with 403 Forbidden.")

    # 6. GET /api/auth/me with Valid Token
    print("\n[TEST 6] GET /api/auth/me (Valid Token)...")
    status, data = http_request("GET", "/api/auth/me", token=patient_token)
    assert status == 200, f"Expected 200 OK, got {status}: {data}"
    assert data["email"] == "test_patient_phase3@example.com", "Email mismatch!"
    print(f"  -> PASSED: Retrieved user profile: {data['name']} ({data['role']})")

    # 7. GET /api/auth/me with Missing Token (401)
    print("\n[TEST 7] GET /api/auth/me without Token (Expecting 401)...")
    status, data = http_request("GET", "/api/auth/me")
    assert status == 401, f"Expected 401 Unauthorized, got {status}: {data}"
    print(f"  -> PASSED: Rejected missing token with 401.")

    # 8. GET /api/auth/me with Tampered Token (401)
    print("\n[TEST 8] GET /api/auth/me with Tampered Token (Expecting 401)...")
    status, data = http_request("GET", "/api/auth/me", token="tampered.token.here")
    assert status == 401, f"Expected 401 Unauthorized, got {status}: {data}"
    print(f"  -> PASSED: Rejected invalid token with 401.")

    # 9. Doctor Login & RBAC Tests
    print("\n[TEST 9] Doctor Login & RBAC Permissions...")
    doc_login = {
        "email": "test_doctor_phase3@example.com",
        "password": "DoctorPass123!"
    }
    status, data = http_request("POST", "/api/auth/login", body=doc_login)
    assert status == 200, f"Doctor login failed: {status}"
    doc_token = data["access_token"]
    assert data["user"]["role"] == "DOCTOR", "Role was not DOCTOR"

    # Doctor accessing Doctor route -> 200
    status, data = http_request("GET", "/api/auth/test/doctor-only", token=doc_token)
    assert status == 200, f"Doctor denied doctor route: {status}"
    print("  -> PASSED: Doctor authorized on doctor route (200 OK).")

    # Doctor accessing Patient route -> 403
    status, data = http_request("GET", "/api/auth/test/patient-only", token=doc_token)
    assert status == 403, f"Doctor wrongly allowed on patient route: {status}"
    print("  -> PASSED: Doctor forbidden on patient route (403 Forbidden).")

    # 10. Patient accessing Doctor & Admin routes -> 403 Forbidden
    print("\n[TEST 10] Patient accessing Doctor & Admin routes (Expecting 403)...")
    status, data = http_request("GET", "/api/auth/test/doctor-only", token=patient_token)
    assert status == 403, f"Patient wrongly allowed on doctor route: {status}"
    status, data = http_request("GET", "/api/auth/test/admin-only", token=patient_token)
    assert status == 403, f"Patient wrongly allowed on admin route: {status}"
    print("  -> PASSED: Patient forbidden from doctor and admin routes (403 Forbidden).")

    # 11. Admin Login & RBAC Tests
    print("\n[TEST 11] Admin Login & Admin RBAC Route...")
    admin_login = {
        "email": "test_admin_phase3@example.com",
        "password": "AdminPass123!"
    }
    status, data = http_request("POST", "/api/auth/login", body=admin_login)
    assert status == 200, f"Admin login failed: {status}"
    admin_token = data["access_token"]
    assert data["user"]["role"] == "ADMIN", "Role was not ADMIN"

    # Admin accessing Admin route -> 200
    status, data = http_request("GET", "/api/auth/test/admin-only", token=admin_token)
    assert status == 200, f"Admin denied admin route: {status}"
    print("  -> PASSED: Admin authorized on admin route (200 OK).")

    print("\n==================================================")
    print("   ALL 11 AUTH & RBAC TESTS PASSED SUCCESSFULLY!  ")
    print("==================================================")


if __name__ == "__main__":
    run_api_tests()

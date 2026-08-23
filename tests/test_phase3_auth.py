"""Comprehensive test suite for Phase 3: Secure Authentication & Role-Based Access Control."""

import sys
import os

# Add backend directory to sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal  # type: ignore # pyright: ignore[reportMissingImports]
from app.models.user import User, UserRole  # type: ignore # pyright: ignore[reportMissingImports]
from app.models.doctor import Doctor  # type: ignore # pyright: ignore[reportMissingImports]
from app.utils.security import hash_password, verify_password, create_access_token, decode_access_token  # type: ignore # pyright: ignore[reportMissingImports]
from datetime import timedelta


def run_tests():
    print("==================================================")
    print("  RUNNING PHASE 3 AUTHENTICATION & RBAC TESTS     ")
    print("==================================================")

    db = SessionLocal()
    try:
        # Test 1: Password hashing and verification
        print("\n[TEST 1] Password Hashing & Verification (bcrypt)...")
        plain = "SecurePassword123!"
        hashed = hash_password(plain)
        assert hashed != plain, "Password was not hashed!"
        assert verify_password(plain, hashed) is True, "Password verification failed!"
        assert verify_password("WrongPassword", hashed) is False, "Wrong password verified as True!"
        print("  -> PASSED: bcrypt hashing and verification working correctly.")

        # Test 2: JWT Creation & Decoding
        print("\n[TEST 2] JWT Token Generation & Validation...")
        payload = {"user_id": 999, "sub": "999", "role": "PATIENT"}
        token = create_access_token(payload, expires_delta=timedelta(minutes=5))
        decoded = decode_access_token(token)
        assert decoded["user_id"] == 999, "User ID mismatch in JWT payload!"
        assert decoded["role"] == "PATIENT", "Role mismatch in JWT payload!"
        assert "exp" in decoded, "Expiration field missing in JWT!"
        print("  -> PASSED: JWT generated and validated with correct payload.")

        # Test 3: Clean up test accounts
        test_emails = [
            "test_patient_phase3@example.com",
            "test_doctor_phase3@example.com",
            "test_admin_phase3@example.com",
            "test_inactive_phase3@example.com"
        ]
        db.query(User).filter(User.email.in_(test_emails)).delete(synchronize_session=False)
        db.commit()

        # Test 4: Seed Doctor & Admin for RBAC testing
        print("\n[TEST 3] Seeding test Doctor and Admin accounts...")
        doctor_user = User(
            name="Dr. Sarah Connor",
            email="test_doctor_phase3@example.com",
            password_hash=hash_password("DoctorPass123!"),
            role=UserRole.DOCTOR,
            phone="1234567890",
            is_active=True
        )
        admin_user = User(
            name="Admin System",
            email="test_admin_phase3@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
            phone="9876543210",
            is_active=True
        )
        inactive_user = User(
            name="Inactive User",
            email="test_inactive_phase3@example.com",
            password_hash=hash_password("InactivePass123!"),
            role=UserRole.PATIENT,
            is_active=False
        )
        db.add_all([doctor_user, admin_user, inactive_user])
        db.commit()
        db.refresh(doctor_user)
        db.refresh(admin_user)
        db.refresh(inactive_user)

        # Create doctor profile record
        doctor_profile = Doctor(
            user_id=doctor_user.id,
            specialization="Cardiology",
            qualification="MD, MBBS",
            experience=10,
            slot_duration=30,
            is_active=True
        )
        db.add(doctor_profile)
        db.commit()
        print("  -> PASSED: Seeded test doctor, admin, and inactive accounts.")

    finally:
        db.close()

    print("\nAll database pre-test setup completed successfully!")


if __name__ == "__main__":
    run_tests()

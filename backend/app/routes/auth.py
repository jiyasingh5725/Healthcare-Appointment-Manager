from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    TokenResponse,
    UserProfileUpdateRequest,
)
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
)
from app.utils.dependencies import (
    get_current_user,
    require_patient,
    require_doctor,
    require_admin,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Public Patient Registration"
)
def register_patient(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new patient account.
    Public registration is strictly limited to the PATIENT role.
    """
    normalized_email = payload.email.lower().strip()

    # Check for duplicate email
    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists.",
        )

    # Hash the password securely
    hashed_pwd = hash_password(payload.password)

    # Create new patient user
    new_user = User(
        name=payload.name.strip(),
        email=normalized_email,
        password_hash=hashed_pwd,
        role=UserRole.PATIENT,  # Forced PATIENT role
        phone=payload.phone.strip() if payload.phone else None,
        is_active=True,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User Login"
)
def login_user(payload: UserLoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate user credentials and return a signed JWT access token.
    """
    normalized_email = payload.email.lower().strip()

    user = db.query(User).filter(User.email == normalized_email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact system administration.",
        )

    # Issue JWT containing user_id, role, and expiration
    token_payload = {
        "user_id": user.id,
        "sub": str(user.id),
        "role": user.role.value,
        "email": user.email,
    }
    access_token = create_access_token(data=token_payload)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Current Authenticated User Profile"
)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Retrieve profile of currently authenticated user.
    """
    return current_user


@router.put(
    "/profile",
    response_model=UserResponse,
    summary="Update Current User Profile"
)
def update_profile(
    payload: UserProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update profile details for the currently authenticated user.
    """
    if payload.name is not None and payload.name.strip():
        current_user.name = payload.name.strip()
    if payload.phone is not None:
        current_user.phone = payload.phone.strip() if payload.phone.strip() else None

    db.commit()
    db.refresh(current_user)
    return current_user



# RBAC Verification Endpoints
@router.get("/test/patient-only", summary="Patient RBAC Test Route")
def test_patient_route(user: User = Depends(require_patient)):
    return {"message": f"Hello Patient {user.name}, your access is verified.", "role": user.role}


@router.get("/test/doctor-only", summary="Doctor RBAC Test Route")
def test_doctor_route(user: User = Depends(require_doctor)):
    return {"message": f"Hello Doctor {user.name}, your access is verified.", "role": user.role}


@router.get("/test/admin-only", summary="Admin RBAC Test Route")
def test_admin_route(user: User = Depends(require_admin)):
    return {"message": f"Hello Admin {user.name}, your access is verified.", "role": user.role}

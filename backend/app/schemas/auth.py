from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.user import UserRole


class UserRegisterRequest(BaseModel):
    """Schema for public patient registration."""
    name: str = Field(..., min_length=2, max_length=120, description="Full name of the user")
    email: EmailStr = Field(..., description="Unique email address")
    password: str = Field(..., min_length=6, max_length=128, description="Password (at least 6 characters)")
    phone: Optional[str] = Field(None, max_length=30, description="Contact phone number")


class UserLoginRequest(BaseModel):
    """Schema for user login credentials."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=1, description="User password")


class UserResponse(BaseModel):
    """Public user response schema."""
    id: int
    name: str
    email: str
    role: UserRole
    phone: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """JWT Token response schema."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserProfileUpdateRequest(BaseModel):
    """Schema for updating user profile details."""
    name: Optional[str] = Field(None, min_length=2, max_length=120, description="Full name")
    phone: Optional[str] = Field(None, max_length=30, description="Contact phone number")


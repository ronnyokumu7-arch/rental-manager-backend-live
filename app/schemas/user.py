# app/schemas/user.py
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from app.models.users import UserRole

class UserBase(BaseModel):
    tenant_id: Optional[int] = None
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    role: UserRole = UserRole.tenant_staff
    is_active: bool = True
    is_suspended: bool = False

    phone_number: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)
    two_factor_enabled: bool = False

    id_number: Optional[str] = None
    dl_number: Optional[str] = None
    dl_expiry: Optional[date] = None
    
    # ✅ NEW: Image URLs for V1 (Base64 or external URLs)
    avatar_url: Optional[str] = None
    id_image_url: Optional[str] = None
    dl_image_url: Optional[str] = None

class UserCreate(UserBase):
    # ✅ Made optional so we can create "Pending Invite" users without a password
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)

class UserUpdate(BaseModel):
    tenant_id: Optional[int] = None
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    is_suspended: Optional[bool] = None
    suspension_reason: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)

    phone_number: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    permissions: Optional[List[str]] = None
    two_factor_enabled: Optional[bool] = None

    id_number: Optional[str] = None
    dl_number: Optional[str] = None
    dl_expiry: Optional[date] = None

    # ✅ NEW: Image URLs
    avatar_url: Optional[str] = None
    id_image_url: Optional[str] = None
    dl_image_url: Optional[str] = None

    # ✅ Verification & Security Fields
    email_verified: Optional[bool] = None
    phone_verified: Optional[bool] = None
    account_locked_until: Optional[datetime] = None
    
    # ✅ Invite Lifecycle Updates
    invite_token: Optional[str] = None
    invite_expires_at: Optional[datetime] = None
    is_onboarded: Optional[bool] = None

    # UI Preferences
    theme_preference: Optional[str] = Field(None, max_length=20)
    density_preference: Optional[str] = Field(None, max_length=20)

class UserOut(BaseModel):
    id: int
    tenant_id: Optional[int] = None
    full_name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    is_suspended: bool = False
    suspension_reason: Optional[str] = None

    phone_number: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)
    two_factor_enabled: bool = False
    last_login_at: Optional[datetime] = None

    id_number: Optional[str] = None
    dl_number: Optional[str] = None
    dl_expiry: Optional[date] = None

    created_at: datetime
    updated_at: datetime

    # ✅ NEW: Image URLs
    avatar_url: Optional[str] = None
    id_image_url: Optional[str] = None
    dl_image_url: Optional[str] = None

    # ✅ Verification & Security Audit Fields
    email_verified: bool = False
    phone_verified: bool = False
    failed_login_attempts: int = 0
    account_locked_until: Optional[datetime] = None

    # ✅ Expose Invite State to Frontend (for "Pending" badges)
    invite_token: Optional[str] = None
    invite_expires_at: Optional[datetime] = None
    is_onboarded: bool = False

    # UI Preferences
    theme_preference: Optional[str] = "system"
    density_preference: Optional[str] = "comfortable"
    
    # ✅ NEW: Agency Owner Flag for Frontend UI (Golden Badge)
    is_tenant_owner: bool = False

    model_config = {"from_attributes": True}

# ✅ COMPLETELY REWRITTEN: Self-Service Onboarding Payload
class AcceptInvitePayload(BaseModel):
    invite_token: str
    password: str = Field(min_length=8, max_length=128)
    
    # Identity
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone_number: Optional[str] = None
    avatar_url: Optional[str] = None
    
    # Compliance (ID is generally required for staff, DL is conditional)
    id_number: Optional[str] = None
    id_image_url: Optional[str] = None
    dl_number: Optional[str] = None
    dl_image_url: Optional[str] = None
    dl_expiry: Optional[date] = None

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from app.models.users import UserRole

class UserBase(BaseModel):
    tenant_id: Optional[int] = None
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    role: UserRole = UserRole.tenant_staff
    is_active: bool = True
    
    # ✅ NEW FIELDS
    phone_number: Optional[str] = None
    department: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)
    two_factor_enabled: bool = False

class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)

class UserUpdate(BaseModel):
    tenant_id: Optional[int] = None
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    
    # ✅ NEW FIELDS
    phone_number: Optional[str] = None
    department: Optional[str] = None
    permissions: Optional[List[str]] = None
    two_factor_enabled: Optional[bool] = None

class UserOut(BaseModel):
    id: int
    tenant_id: Optional[int] = None
    full_name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    is_suspended: bool = False
    suspension_reason: Optional[str] = None
    
    # ✅ NEW FIELDS
    phone_number: Optional[str] = None
    department: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)
    two_factor_enabled: bool = False
    last_login_at: Optional[datetime] = None
    
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}

# app/schemas/tenant.py
import enum
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.tenants import PaymentMethodType, SubscriptionStatus


# ---------------------------------------------------------------------------
# Base & Input Schemas
# ---------------------------------------------------------------------------

class TenantBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=150, description="Agency or company name")
    email: EmailStr = Field(..., description="Primary contact/billing email")
    phone_number: Optional[str] = Field(None, max_length=30, description="Primary contact / M-Pesa number")

    @field_validator("name", "email", "phone_number", mode="before")
    @classmethod
    def strip_strings(cls, v):
        if isinstance(v, str):
            cleaned = v.strip()
            return cleaned if cleaned else None
        return v


class TenantCreate(TenantBase):
    """Maps directly to the 4-step Onboarding Wizard payload."""
    
    # ✅ NEW: Denormalized Admin Snapshot (for zero-join Super Admin lookups)
    admin_name: str = Field(..., min_length=2, max_length=150, description="Initial Tenant Admin full name")
    admin_email: EmailStr = Field(..., description="Initial Tenant Admin email (used for auth & display)")
    admin_phone: Optional[str] = Field(None, max_length=30, description="Initial Tenant Admin direct phone")
    password: str = Field(..., min_length=8, description="Initial Tenant Admin password (min 8 chars)")
    
    # Core Identity (Step 1)
    is_corporate: bool = Field(default=False, description="Whether agency is registered corporate entity")
    business_location: Optional[str] = Field(None, max_length=255, description="Physical office or yard address")
    
    # Compliance & Locale (Step 2)
    kra_pin: Optional[str] = Field(None, max_length=20, description="KRA PIN for tax invoicing in Kenya")
    currency: str = Field(default="KES", max_length=10, description="Default operational currency")
    time_zone: str = Field(default="Africa/Nairobi", max_length=50, description="Tenant primary time zone")
    
    # Subscription & Billing (Step 3)
    plan: str = Field(default="free_trial", description="Initial plan tier")
    billing_cycle: Optional[str] = Field(default="monthly", description="Monthly or annual billing preference")

    # Optional payment gateway setup
    default_payment_method: Optional[PaymentMethodType] = None
    stripe_customer_id: Optional[str] = None
    paypal_payer_id: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None

    @field_validator("admin_name", "admin_email", "admin_phone", mode="before")
    @classmethod
    def strip_admin_strings(cls, v):
        if isinstance(v, str):
            cleaned = v.strip()
            return cleaned if cleaned else None
        return v


class TenantUpdate(BaseModel):
    """Super Admin update for specific tenant configuration."""
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, max_length=30)
    
    # ✅ NEW: Allow updating the denormalized admin snapshot
    admin_name: Optional[str] = Field(None, min_length=2, max_length=150)
    admin_email: Optional[EmailStr] = None
    admin_phone: Optional[str] = Field(None, max_length=30)
    
    # Lifecycle Management
    is_active: Optional[bool] = None
    is_archived: Optional[bool] = None
    
    # Subscription Management
    plan: Optional[str] = None
    subscription_status: Optional[SubscriptionStatus] = None
    
    # Payment Gateway Updates
    default_payment_method: Optional[PaymentMethodType] = None
    stripe_customer_id: Optional[str] = None
    paypal_payer_id: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None

    @field_validator("name", "email", "phone_number", "admin_name", "admin_email", "admin_phone", mode="before")
    @classmethod
    def strip_strings(cls, v):
        if isinstance(v, str):
            cleaned = v.strip()
            return cleaned if cleaned else None
        return v


# ---------------------------------------------------------------------------
# Output Schemas
# ---------------------------------------------------------------------------

class TenantProfileOut(BaseModel):
    """Nested profile data returned with tenant details."""
    id: int
    tenant_id: int
    company_name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    tax_number: Optional[str] = None  # KRA PIN
    logo_url: Optional[str] = None
    contract_prefix: str
    contract_footer: Optional[str] = None

    model_config = {"from_attributes": True}


class TenantOut(TenantBase):
    """Unified output for Super Admin table AND tenant self-service views."""
    id: int
    
    # ✅ NEW: Denormalized Admin Snapshot (instant access, no user join needed)
    admin_name: Optional[str] = None
    admin_email: Optional[str] = None
    admin_phone: Optional[str] = None
    
    # Lifecycle & Multi-Tenancy
    is_active: bool
    is_archived: bool = False
    suspended_at: Optional[datetime] = None
    suspension_reason: Optional[str] = None
    
    # Subscription & Billing
    plan: str
    subscription_status: SubscriptionStatus
    trial_ends_at: Optional[datetime] = None
    subscription_ends_at: Optional[datetime] = None
    grace_period_ends_at: Optional[datetime] = None
    
    # Payment Gateway
    default_payment_method: Optional[PaymentMethodType] = None
    stripe_customer_id: Optional[str] = None
    paypal_payer_id: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None
    
    # Nested Profile Data (Joined from TenantProfile table)
    profile: Optional[TenantProfileOut] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

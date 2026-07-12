# app/schemas/tenant.py
import enum
from datetime import datetime
from typing import Any, Dict, Optional, List

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
            return v.strip() or None
        return v


class TenantCreate(TenantBase):
    """Maps directly to the 4-step Onboarding Wizard payload."""
    
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
    
    # Initial Tenant Admin Setup (Step 4)
    admin_name: Optional[str] = Field(None, max_length=150, description="Initial Tenant Admin full name")
    admin_phone: Optional[str] = Field(None, max_length=30, description="Initial Tenant Admin direct phone")
    password: str = Field(..., min_length=8, description="Initial Tenant Admin password (min 8 chars)")

    # Optional payment gateway setup
    default_payment_method: Optional[PaymentMethodType] = None
    stripe_customer_id: Optional[str] = None
    paypal_payer_id: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None


class TenantUpdate(BaseModel):
    """Super Admin update for specific tenant configuration."""
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, max_length=30)
    
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

    @field_validator("name", "email", "phone_number", mode="before")
    @classmethod
    def strip_strings(cls, v):
        if isinstance(v, str):
            return v.strip() or None
        return v


# ---------------------------------------------------------------------------
# Output Schemas
# ---------------------------------------------------------------------------

class TenantProfileOut(BaseModel):
    """Nested profile data returned with tenant details."""
    id: int
    tenant_id: int
    business_location: Optional[str] = None
    kra_pin: Optional[str] = None
    currency: str = "KES"
    time_zone: str = "Africa/Nairobi"
    is_corporate: bool = False
    contract_prefix: str
    contract_terms: Optional[str] = None

    model_config = {"from_attributes": True}


class TenantOut(TenantBase):
    """Unified output for Super Admin table AND tenant self-service views."""
    id: int
    is_active: bool
    is_archived: bool = False  # Multi-tenancy vault support
    suspended_at: Optional[datetime] = None
    suspension_reason: Optional[str] = None
    
    plan: str
    subscription_status: SubscriptionStatus
    
    trial_ends_at: Optional[datetime] = None
    subscription_ends_at: Optional[datetime] = None
    grace_period_ends_at: Optional[datetime] = None
    
    default_payment_method: Optional[PaymentMethodType] = None
    stripe_customer_id: Optional[str] = None
    paypal_payer_id: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None
    
    # Nested Profile Data (Joined from TenantProfile table)
    profile: Optional[TenantProfileOut] = None
    
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

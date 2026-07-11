import enum
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.tenants import PaymentMethodType, SubscriptionStatus


# ---------------------------------------------------------------------------
# Base & Input Schemas
# ---------------------------------------------------------------------------

class TenantBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=150, description="Agency or company name")
    email: EmailStr = Field(..., description="Primary contact/billing email")
    phone_number: Optional[str] = Field(None, description="Primary contact / M-Pesa phone number")


class TenantCreate(TenantBase):
    plan: str = Field(default="free_trial", description="Initial plan tier")
    
    # Optional payment setup at onboarding
    default_payment_method: Optional[PaymentMethodType] = None
    stripe_customer_id: Optional[str] = None
    paypal_payer_id: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    is_active: Optional[bool] = None
    plan: Optional[str] = None
    subscription_status: Optional[SubscriptionStatus] = None
    
    # Optional payment update fields
    default_payment_method: Optional[PaymentMethodType] = None
    stripe_customer_id: Optional[str] = None
    paypal_payer_id: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Output Schemas
# ---------------------------------------------------------------------------

class TenantOut(TenantBase):
    id: int
    is_active: bool
    plan: str
    subscription_status: SubscriptionStatus
    
    # Trial & Subscription Lifecycle Timestamps
    trial_ends_at: Optional[datetime] = None
    subscription_ends_at: Optional[datetime] = None
    grace_period_ends_at: Optional[datetime] = None
    
    # Optional Payment Method Info
    default_payment_method: Optional[PaymentMethodType] = None
    stripe_customer_id: Optional[str] = None
    paypal_payer_id: Optional[str] = None
    payment_metadata: Optional[Dict[str, Any]] = None
    
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

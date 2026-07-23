# app/schemas/payment.py
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any

from pydantic import BaseModel, computed_field, Field

from app.models.payments import PaymentMethod, PaymentStatus, VerificationStatus


class PaymentCreate(BaseModel):
    amount: Decimal
    currency_code: str = "KES"
    method: PaymentMethod
    reference: Optional[str] = None
    notes: Optional[str] = None


class PaymentVoid(BaseModel):
    reason: str


class PaymentOut(BaseModel):
    id: int
    invoice_id: int
    tenant_id: int
    amount: Decimal
    currency_code: str
    method: PaymentMethod
    reference: Optional[str] = None
    status: PaymentStatus
    paid_at: Optional[datetime] = None
    recorded_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime

    invoice: Optional[Any] = Field(default=None, exclude=True)

    @computed_field
    @property
    def invoice_number(self) -> Optional[str]:
        if self.invoice:
            return self.invoice.invoice_number
        return None

    @computed_field
    @property
    def booking_id(self) -> Optional[int]:
        if self.invoice:
            return self.invoice.booking_id
        return None

    @computed_field
    @property
    def client_id(self) -> Optional[int]:
        if self.invoice and getattr(self.invoice, 'booking', None) and getattr(self.invoice.booking, 'client', None):
            return self.invoice.booking.client.id
        return None

    @computed_field
    @property
    def client_name(self) -> Optional[str]:
        if self.invoice and getattr(self.invoice, 'booking', None) and getattr(self.invoice.booking, 'client', None):
            return self.invoice.booking.client.full_name
        return None

    model_config = {"from_attributes": True}


class PublicPaymentCreate(BaseModel):
    amount: Decimal
    currency_code: str = "KES"
    method: PaymentMethod
    reference: Optional[str] = None
    notes: Optional[str] = None


class PaymentVerificationCreate(BaseModel):
    target_plan: str = Field(..., description="Target plan ID: starter, pro, enterprise")
    target_billing_cycle: str = Field("monthly", description="monthly | annual")
    payment_method: PaymentMethod = Field(..., description="mpesa or bank")
    reference_code: str = Field(..., min_length=3, max_length=100, description="M-Pesa transaction code or Bank reference")
    notes: Optional[str] = None


class PaymentVerificationReview(BaseModel):
    # ✅ FIX: Added status field so the router can read payload.status
    status: VerificationStatus = Field(..., description="The new status: 'approved' or 'rejected'")
    rejection_reason: Optional[str] = Field(None, description="Required if rejecting verification request")


class PaymentVerificationOut(BaseModel):
    id: int
    tenant_id: int
    target_plan: str
    target_billing_cycle: str
    payment_method: PaymentMethod
    reference_code: str
    notes: Optional[str] = None
    status: VerificationStatus
    rejection_reason: Optional[str] = None
    reviewed_by_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # ✅ TRUTH-BASED FIX: Explicit standard field. No computed magic.
    # We will populate this manually in the router to guarantee it works.
    tenant_name: Optional[str] = None

    model_config = {"from_attributes": True}

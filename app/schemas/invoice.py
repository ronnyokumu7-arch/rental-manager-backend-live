from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, computed_field

from app.models.invoices import InvoiceStatus


class InvoiceCreate(BaseModel):
    booking_id: int
    due_date: datetime
    notes: Optional[str] = None
    amount_due: Optional[Decimal] = None
    currency_code: Optional[str] = "KES"
    discount_amount: Optional[Decimal] = Decimal("0")
    discount_reason: Optional[str] = None


class InvoiceUpdate(BaseModel):
    notes: Optional[str] = None
    status: Optional[InvoiceStatus] = None
    amount_due: Optional[Decimal] = None
    due_date: Optional[datetime] = None
    currency_code: Optional[str] = None
    discount_amount: Optional[Decimal] = None
    discount_reason: Optional[str] = None


class InvoiceOut(BaseModel):
    id: int
    tenant_id: int
    booking_id: Optional[int] = None
    invoice_number: str
    status: InvoiceStatus
    amount_due: Decimal
    amount_paid: Decimal
    currency_code: str
    due_date: datetime
    paid_at: Optional[datetime] = None
    pdf_path: Optional[str] = None
    notes: Optional[str] = None
    share_token: Optional[str] = None
    share_token_expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    discount_amount: Decimal
    discount_reason: Optional[str] = None

    @computed_field
    @property
    def remaining_balance(self) -> Decimal:
        return max(Decimal("0"), self.amount_due - (self.amount_paid or Decimal("0")))

    model_config = {"from_attributes": True}

import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, Enum as SAEnum, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class InvoiceStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    partially_paid = "partially_paid"
    paid = "paid"
    overdue = "overdue"
    void = "void"


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True, index=True)

    invoice_number = Column(String(20), unique=True, nullable=False, index=True)
    status = Column(SAEnum(InvoiceStatus), default=InvoiceStatus.draft, nullable=False)

    amount_due = Column(Numeric(12, 2), default=0, nullable=False)
    amount_paid = Column(Numeric(12, 2), default=0, nullable=False)
    currency_code = Column(String(3), default="KES", nullable=False)

    discount_amount = Column(Numeric(12, 2), default=0, nullable=False)
    discount_reason = Column(Text, nullable=True)

    due_date = Column(DateTime(timezone=True), nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    notes = Column(String(500), nullable=True)
    pdf_path = Column(String(500), nullable=True)

    share_token = Column(String(36), unique=True, nullable=True, index=True)
    share_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    booking = relationship("Booking", back_populates="invoices")
    tenant = relationship("Tenant", back_populates="invoices")
    payments = relationship("Payment", back_populates="invoice")

    @property
    def remaining_balance(self) -> Decimal:
        return max(Decimal("0"), self.amount_due - (self.amount_paid or Decimal("0")))

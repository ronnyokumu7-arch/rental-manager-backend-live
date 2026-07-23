# app/models/payments.py
import enum
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base

class PaymentMethod(str, enum.Enum):
    mpesa = "mpesa"
    airtel_money = "airtel_money"
    card = "card"
    paypal = "paypal"
    bank = "bank"
    manual = "manual"

class PaymentStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    void = "void"

class VerificationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

class Payment(Base):
    """Customer rental invoice payments."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    currency_code = Column(String(3), nullable=False, default="KES", server_default="KES")
    method = Column(Enum(PaymentMethod), nullable=False)
    reference = Column(String, nullable=True)
    status = Column(
        Enum(PaymentStatus),
        nullable=False,
        default=PaymentStatus.pending,
        server_default=PaymentStatus.pending.value,
    )
    paid_at = Column(DateTime(timezone=True), nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    invoice = relationship("Invoice", back_populates="payments")
    tenant = relationship("Tenant", back_populates="payments")
    recorded_by_user = relationship("User", back_populates="recorded_payments")

class PaymentVerification(Base):
    """SaaS Tenant Subscription M-Pesa / Bank Wire manual verification requests."""
    __tablename__ = "payment_verifications"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    target_plan = Column(String(50), nullable=False)  # e.g., starter, pro, enterprise
    target_billing_cycle = Column(String(20), nullable=False, default="monthly")  # monthly | annual
    payment_method = Column(Enum(PaymentMethod), nullable=False)  # mpesa or bank
    
    # Enforce uniqueness across all submissions to stop reused transaction codes
    reference_code = Column(String(100), unique=True, nullable=False, index=True)
    notes = Column(Text, nullable=True)
    
    status = Column(
        Enum(VerificationStatus),
        nullable=False,
        default=VerificationStatus.pending,
        server_default=VerificationStatus.pending.value,
        index=True
    )
    rejection_reason = Column(Text, nullable=True)
    
    reviewed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    tenant = relationship("Tenant", back_populates="payment_verifications")
    reviewed_by = relationship("User", foreign_keys="[PaymentVerification.reviewed_by_id]")

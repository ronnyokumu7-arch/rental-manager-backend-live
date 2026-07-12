# app/models/tenants.py
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, JSON, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base


class SubscriptionStatus(str, enum.Enum):
    trial = "trial"
    starter_trial = "starter_trial"
    active = "active"
    past_due = "past_due"
    suspended = "suspended"
    cancelled = "cancelled"


class PaymentMethodType(str, enum.Enum):
    mpesa = "mpesa"
    card = "card"
    paypal = "paypal"
    bank = "bank"


class Tenant(Base):
    __tablename__ = "tenants"
    
    # Primary Keys & Identity
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone_number = Column(String(30), nullable=True)  # Primary contact / M-Pesa number
    
    # -----------------------------------------------------------------------
    # ✅ NEW: Denormalized Admin Snapshot (for zero-join Super Admin lookups)
    # -----------------------------------------------------------------------
    admin_name = Column(String(150), nullable=True)
    admin_email = Column(String(255), nullable=True)
    admin_phone = Column(String(30), nullable=True)
    
    # -----------------------------------------------------------------------
    # Lifecycle & Multi-Tenancy (Vault/Suspension)
    # -----------------------------------------------------------------------
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    is_archived = Column(Boolean, nullable=False, default=False, server_default="false")
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspension_reason = Column(Text, nullable=True)
    
    # -----------------------------------------------------------------------
    # Subscription & Billing
    # -----------------------------------------------------------------------
    plan = Column(String(50), nullable=False, default="free_trial", server_default="free_trial")
    subscription_status = Column(
        Enum(SubscriptionStatus),
        nullable=False,
        default=SubscriptionStatus.trial,
        server_default=SubscriptionStatus.trial.value,
    )
    
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    subscription_ends_at = Column(DateTime(timezone=True), nullable=True)
    grace_period_ends_at = Column(DateTime(timezone=True), nullable=True)

    # Payment Gateway Readiness
    default_payment_method = Column(Enum(PaymentMethodType), nullable=True)
    stripe_customer_id = Column(String(100), nullable=True, index=True)
    paypal_payer_id = Column(String(100), nullable=True)
    payment_metadata = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    clients = relationship("Client", back_populates="tenant", cascade="all, delete-orphan")
    vehicles = relationship("Vehicle", back_populates="tenant", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="tenant", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="tenant", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="tenant", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="tenant", cascade="all, delete-orphan")
    profile = relationship("TenantProfile", back_populates="tenant", uselist=False, cascade="all, delete-orphan")
    policies = relationship("TenantPolicy", back_populates="tenant", cascade="all, delete-orphan")
    contracts = relationship("Contract", back_populates="tenant", cascade="all, delete-orphan")

    # ✅ FIX: Composite index for Super Admin search + vault filtering performance
    __table_args__ = (
        Index('ix_tenants_search_vault', 'is_archived', 'name'),
    )

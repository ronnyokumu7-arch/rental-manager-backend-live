# app/models/subscription.py
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class PlanType(str, enum.Enum):
    free_trial = "free_trial"
    starter_trial = "starter_trial"
    pay_as_you_go = "pay_as_you_go"
    starter = "starter"
    pro = "pro"
    enterprise = "enterprise"


class BillingCycle(str, enum.Enum):
    trial = "trial"
    pay_as_you_go = "pay_as_you_go"
    monthly = "monthly"
    annual = "annual"


class SubscriptionStatus(str, enum.Enum):
    trial = "trial"
    starter_trial = "starter_trial"
    active = "active"
    pending_verification = "pending_verification"  # ✅ NEW: Flagged during manual M-Pesa / Bank code review
    past_due = "past_due"
    suspended = "suspended"
    cancelled = "cancelled"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    plan = Column(Enum(PlanType), nullable=False, default=PlanType.free_trial)
    billing_cycle = Column(Enum(BillingCycle), nullable=False, default=BillingCycle.trial)
    status = Column(
        Enum(SubscriptionStatus),
        nullable=False,
        default=SubscriptionStatus.trial,
        server_default=SubscriptionStatus.trial.value,
    )
    
    starts_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ends_at = Column(DateTime(timezone=True), nullable=True)
    grace_period_ends_at = Column(DateTime(timezone=True), nullable=True)
    
    # Fast UI state sync for toggle switch
    auto_renew = Column(Boolean, nullable=False, default=True, server_default="true")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    tenant = relationship("Tenant", back_populates="subscriptions")

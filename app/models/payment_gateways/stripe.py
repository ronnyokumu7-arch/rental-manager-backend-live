# app/models/payment/bank.py
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.db.database import Base

class StripeConfig(Base):
    __tablename__ = "stripe_configs"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)
    publishable_key = Column(String(255), nullable=False)
    secret_key = Column(String(255), nullable=False)
    webhook_secret = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=False)
    tenant = relationship("Tenant", back_populates="stripe_config")

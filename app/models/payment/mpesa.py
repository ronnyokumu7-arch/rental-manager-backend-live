# app/models/payment/mpesa.py
import enum
from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.db.database import Base


class MpesaEnvironment(str, enum.Enum):
    sandbox = "sandbox"
    production = "production"


class MpesaConfig(Base):
    __tablename__ = "mpesa_configs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    business_shortcode = Column(String(20), nullable=False)
    till_number = Column(String(20), nullable=True)
    consumer_key = Column(String(255), nullable=False)
    consumer_secret = Column(String(255), nullable=False)
    passkey = Column(String(255), nullable=False)
    environment = Column(
        Enum(MpesaEnvironment),
        nullable=False,
        default=MpesaEnvironment.sandbox,
    )
    callback_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    tenant = relationship("Tenant", back_populates="mpesa_config")

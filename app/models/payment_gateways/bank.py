# app/models/payment/bank.py
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.db.database import Base


class BankAccountConfig(Base):
    __tablename__ = "bank_account_configs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    bank_name = Column(String(150), nullable=False)
    account_name = Column(String(255), nullable=False)
    account_number = Column(String(50), nullable=False)
    branch_code = Column(String(20), nullable=True)
    swift_code = Column(String(20), nullable=True)
    currency = Column(String(10), nullable=False, default="KES")
    is_primary = Column(Boolean, nullable=False, default=True)

    tenant = relationship("Tenant", back_populates="bank_accounts")

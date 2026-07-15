import enum
from sqlalchemy import Boolean, Column, Date, DateTime, Enum, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base

class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    tenant_admin = "tenant_admin"
    tenant_staff = "tenant_staff"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    
    # Core Identity
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    # UI Preferences
    theme_preference = Column(String(20), nullable=True, default="system", server_default="system")  # "light", "dark", "system"
    density_preference = Column(String(20), nullable=True, default="comfortable", server_default="comfortable")  # "comfortable", "compact"
    
    # Contact & Role Details
    phone_number = Column(String, nullable=True)
    department = Column(String, nullable=True)  # e.g., "Operations", "Finance & Accounts"
    job_title = Column(String, nullable=True)   # e.g., "Driver", "Fleet Manager", "Accountant"
    
    # Security & Access (Upgraded to JSONB)
    permissions = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    two_factor_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    
    # Compliance (Required for Drivers/Staff)
    id_number = Column(String, nullable=True)
    dl_number = Column(String, nullable=True)
    dl_expiry = Column(Date, nullable=True)
    
    # Account Status
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    is_suspended = Column(Boolean, nullable=False, default=False, server_default="false")
    suspension_reason = Column(String, nullable=True)
    
    role = Column(
        Enum(UserRole),
        nullable=False,
        default=UserRole.tenant_staff,
        server_default=UserRole.tenant_staff.value,
    )
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    tenant = relationship("Tenant", back_populates="users", foreign_keys="[User.tenant_id]")
    recorded_payments = relationship("Payment", back_populates="recorded_by_user")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="user", cascade="all, delete-orphan")

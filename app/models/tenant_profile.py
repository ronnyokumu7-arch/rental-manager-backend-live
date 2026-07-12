# app/models/tenant_profile.py
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class TenantProfile(Base):
    __tablename__ = "tenant_profiles"

    id = Column(Integer, primary_key=True, index=True)
    
    # One-to-one relationship with Tenant (CASCADE ensures profile is deleted when tenant is removed)
    tenant_id = Column(
        Integer, 
        ForeignKey("tenants.id", ondelete="CASCADE"), 
        nullable=False, 
        unique=True, 
        index=True
    )
    
    # Identity & Contact (Mirrors Tenant base fields for contract/invoice generation)
    company_name = Column(String(150), nullable=False, index=True)
    address = Column(Text, nullable=True)  # Maps to wizard.business_location
    phone = Column(String(30), nullable=True)
    email = Column(String(255), nullable=True)
    website = Column(String(255), nullable=True)
    
    # Compliance & Taxation
    tax_number = Column(String(20), nullable=True, index=True)  # Maps to wizard.kra_pin
    
    # Branding & Contracts
    logo_url = Column(String(500), nullable=True)
    contract_prefix = Column(String(10), nullable=False, default="T0000")
    contract_footer = Column(Text, nullable=True)  # Maps to wizard.contract_terms
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    tenant = relationship("Tenant", back_populates="profile")

    # ✅ FIX: Composite index for Super Admin search performance
    __table_args__ = (
        Index('ix_tenant_profiles_search', 'company_name', 'tax_number'),
    )

    def __repr__(self):
        return f"<TenantProfile(id={self.id}, tenant_id={self.tenant_id}, prefix='{self.contract_prefix}')>"

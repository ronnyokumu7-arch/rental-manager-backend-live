# app/schemas/tenant_profile.py
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class TenantProfileBase(BaseModel):
    """Maps to TenantProfile SQLAlchemy model. 
    Uses DB column names directly to avoid serialization mismatches."""
    
    company_name: Optional[str] = Field(None, max_length=150, description="Legal company name (mirrors Tenant.name)")
    address: Optional[str] = Field(None, max_length=255, description="Physical office or yard address")
    phone: Optional[str] = Field(None, max_length=30, description="Business contact phone")
    email: Optional[str] = Field(None, max_length=255, description="Business contact email")
    website: Optional[str] = Field(None, max_length=255, description="Company website URL")
    tax_number: Optional[str] = Field(None, max_length=20, description="KRA PIN / Tax Identifier")
    logo_url: Optional[str] = Field(None, max_length=500, description="URL to company logo")
    contract_prefix: str = Field(..., max_length=10, description="Auto-generated prefix e.g. T0001")
    contract_footer: Optional[str] = Field(None, description="Default boilerplate terms for rental agreements")

    @field_validator("tax_number", mode="before")
    @classmethod
    def clean_tax_number(cls, v):
        if isinstance(v, str):
            cleaned = v.strip().upper()
            return cleaned if cleaned else None
        return v


class TenantProfileCreate(TenantProfileBase):
    """Used internally by create_tenant route. Not exposed to frontend directly."""
    pass


class TenantProfileUpdate(BaseModel):
    """For updating profile after initial creation."""
    company_name: Optional[str] = Field(None, max_length=150)
    address: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=255)
    website: Optional[str] = Field(None, max_length=255)
    tax_number: Optional[str] = Field(None, max_length=20)
    logo_url: Optional[str] = Field(None, max_length=500)
    contract_prefix: Optional[str] = Field(None, max_length=10)
    contract_footer: Optional[str] = None

    @field_validator("tax_number", mode="before")
    @classmethod
    def clean_tax_number(cls, v):
        if isinstance(v, str):
            cleaned = v.strip().upper()
            return cleaned if cleaned else None
        return v


class TenantProfileOut(TenantProfileBase):
    id: int
    tenant_id: int

    model_config = {"from_attributes": True}

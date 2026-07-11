from typing import Optional
from pydantic import BaseModel, Field


class TenantProfileBase(BaseModel):
    business_location: Optional[str] = Field(None, max_length=255, description="Physical office or yard address")
    kra_pin: Optional[str] = Field(None, max_length=20, description="KRA PIN for tax invoicing in Kenya")
    currency: str = Field(default="KES", max_length=10, description="Default operational currency (e.g., KES, USD)")
    time_zone: str = Field(default="Africa/Nairobi", max_length=50, description="Tenant primary time zone")
    is_corporate: bool = Field(default=False, description="Whether agency is registered corporate entity")
    contract_terms: Optional[str] = Field(None, description="Default boilerplate terms for rental agreements")


class TenantProfileCreate(TenantProfileBase):
    pass


class TenantProfileUpdate(BaseModel):
    business_location: Optional[str] = Field(None, max_length=255)
    kra_pin: Optional[str] = Field(None, max_length=20)
    currency: Optional[str] = Field(None, max_length=10)
    time_zone: Optional[str] = Field(None, max_length=50)
    is_corporate: Optional[bool] = None
    contract_terms: Optional[str] = None
    contract_prefix: Optional[str] = Field(None, max_length=10)


class TenantProfileOut(TenantProfileBase):
    id: int
    tenant_id: int
    contract_prefix: str

    model_config = {"from_attributes": True}

# app/schemas/vehicle.py
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field
from app.models.vehicles import VehicleStatus

class VehicleBase(BaseModel):
    make: str
    model: str
    year: int
    plate_number: str
    vin: Optional[str] = None
    daily_rate: Decimal
    current_mileage: int = 0
    next_service_km: Optional[int] = None
    insurance_number: Optional[str] = None
    insurance_expiry: Optional[datetime] = None
    notes: Optional[str] = None

class VehicleCreate(VehicleBase):
    pass

class VehicleUpdate(BaseModel):
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    plate_number: Optional[str] = None
    vin: Optional[str] = None
    daily_rate: Optional[Decimal] = None
    status: Optional[VehicleStatus] = None
    current_mileage: Optional[int] = None
    next_service_km: Optional[int] = None
    insurance_number: Optional[str] = None
    insurance_expiry: Optional[datetime] = None
    insurance_doc: Optional[str] = None
    registration_doc: Optional[str] = None
    inspection_doc: Optional[str] = None
    notes: Optional[str] = None

class VehicleOut(VehicleBase):
    id: int
    tenant_id: int
    status: VehicleStatus
    insurance_doc: Optional[str] = None
    registration_doc: Optional[str] = None
    inspection_doc: Optional[str] = None
    is_archived: bool
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}

# =============================================================================
# ✅ MILESTONE 3: Payload for resolving the awaiting_mileage lock
# =============================================================================
class MileageUpdatePayload(BaseModel):
    current_mileage: int = Field(gt=0, description="New odometer reading (must be greater than current)")
    next_service_km: Optional[int] = Field(default=None, description="Optional next service interval")

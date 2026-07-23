# backend/app/schemas/contract.py
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, computed_field, Field
from app.models.contracts import ContractStatus

class ContractOut(BaseModel):
    id: int
    booking_id: int
    tenant_id: int
    contract_number: str
    status: ContractStatus
    pdf_path: Optional[str] = None
    signature_image_path: Optional[str] = None
    signed_at: Optional[datetime] = None
    share_token: Optional[str] = None
    share_token_expires_at: Optional[datetime] = None
    signed_by_client: bool = False
    client_signed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    # ✅ CRITICAL FIX: Explicitly declare 'booking' so Pydantic populates it from SQLAlchemy
    booking: Optional[Any] = Field(default=None, exclude=True)
    
    @computed_field
    @property
    def booking_number(self) -> Optional[str]:
        if self.booking:
            return self.booking.booking_number
        return None

    # ✅ ADDED: Extract client data from the linked booking
    @computed_field
    @property
    def client_id(self) -> Optional[int]:
        if self.booking and getattr(self.booking, 'client', None):
            return self.booking.client.id
        return None

    @computed_field
    @property
    def client_name(self) -> Optional[str]:
        if self.booking and getattr(self.booking, 'client', None):
            return self.booking.client.full_name
        return None

    model_config = {"from_attributes": True}


class PublicContractView(BaseModel):
    """Schema for public contract viewing (no auth required)"""
    contract_number: str
    booking_id: int
    booking_number: Optional[str] = None
    tenant_name: str
    client_name: str
    vehicle_make: str
    vehicle_model: str
    vehicle_plate: str
    start_date: str
    end_date: str
    total_amount: str
    currency_code: str
    status: ContractStatus
    signed_by_client: bool
    created_at: datetime


class ContractSignPayload(BaseModel):
    signature: str  # Base64 encoded signature image

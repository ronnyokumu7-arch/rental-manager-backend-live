from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from app.models.quotations import QuotationStatus

class QuotationCreate(BaseModel):
    client_id: int
    vehicle_id: int
    start_date: datetime
    end_date: datetime
    destination: Optional[str] = None
    pickup_location: Optional[str] = None
    return_location: Optional[str] = None
    total_amount: Decimal = Field(gt=0)
    currency_code: str = Field(default="KES", min_length=3, max_length=3)

    @model_validator(mode="after")
    def end_date_must_be_after_start_date(self) -> "QuotationCreate":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self

class QuotationOut(BaseModel):
    id: int
    tenant_id: int
    client_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    destination: Optional[str] = None
    pickup_location: Optional[str] = None
    return_location: Optional[str] = None
    start_date: datetime
    end_date: datetime
    total_amount: Decimal
    currency_code: str
    status: QuotationStatus
    
    # Sharing fields
    share_token: Optional[str] = None
    share_token_expires_at: Optional[datetime] = None
    
    # Lifecycle links
    booking_id: Optional[int] = None
    
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class QuotationPublicView(BaseModel):
    """What the client sees when they open the share link."""
    id: int
    tenant_name: str
    client_name: str
    vehicle_details: str
    start_date: str
    end_date: str
    pickup_location: Optional[str]
    return_location: Optional[str]
    total_amount: str
    currency_code: str
    expires_at: str
    status: str

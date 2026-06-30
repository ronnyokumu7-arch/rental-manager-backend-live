from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from app.models.quotations import QuotationStatus

class QuotationCreate(BaseModel):
    booking_id: int
    client_id: int
    vehicle_id: int
    start_date: datetime
    end_date: datetime
    pickup_location: Optional[str] = None
    return_location: Optional[str] = None
    destination: Optional[str] = None
    daily_rate: Optional[Decimal] = None
    total_amount: Decimal = Field(gt=0)
    currency_code: str = Field(default="KES", min_length=3, max_length=3)
    terms_and_conditions: Optional[str] = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date <= self.start_date:
            raise ValueError('End date must be after start date')
        return self

class QuotationOut(BaseModel):
    id: int
    tenant_id: int
    booking_id: Optional[int] = None
    client_id: int
    vehicle_id: int
    start_date: datetime
    end_date: datetime
    pickup_location: Optional[str] = None
    return_location: Optional[str] = None
    destination: Optional[str] = None
    daily_rate: Optional[Decimal] = None
    total_amount: Decimal
    currency_code: str
    terms_and_conditions: Optional[str] = None
    status: QuotationStatus
    share_token: Optional[str] = None
    share_token_expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class QuotationPublicView(BaseModel):
    id: int
    tenant_name: str
    client_name: str
    vehicle_details: str
    start_date: str
    end_date: str
    pickup_location: Optional[str] = None
    return_location: Optional[str] = None
    destination: Optional[str] = None
    daily_rate: str
    total_amount: str
    currency_code: str
    terms_and_conditions: Optional[str] = None
    status: str
    expires_at: Optional[str] = None

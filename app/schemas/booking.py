from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from app.models.bookings import BookingStatus

class BookingBase(BaseModel):
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

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date <= self.start_date:
            raise ValueError('End date must be after start date')
        return self

class BookingCreate(BookingBase):
    pass

class BookingUpdate(BaseModel):
    client_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    pickup_location: Optional[str] = None
    return_location: Optional[str] = None
    destination: Optional[str] = None
    daily_rate: Optional[Decimal] = Field(default=None, gt=0)
    total_amount: Optional[Decimal] = Field(default=None, gt=0)
    currency_code: Optional[str] = Field(default=None, min_length=3, max_length=3)
    status: Optional[BookingStatus] = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError('End date must be after start date')
        return self

class BookingOut(BaseModel):
    id: int
    tenant_id: int
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
    status: BookingStatus
    is_archived: bool
    quotation_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

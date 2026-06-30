from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from app.models.quotations import QuotationStatus

# ─── CREATE & UPDATE SCHEMAS ────────────────────────────────────────────────

class QuotationCreate(BaseModel):
    client_id: int
    vehicle_id: int
    start_date: datetime
    end_date: datetime
    pickup_location: Optional[str] = None
    return_location: Optional[str] = None
    destination: Optional[str] = None
    
    # Financials (Required by frontend)
    daily_rate: Decimal = Field(gt=0)
    total_amount: Decimal = Field(gt=0)
    currency_code: str = Field(default="KES", min_length=3, max_length=3)
    
    # Terms & Notes
    terms_and_conditions: Optional[str] = None
    admin_notes: Optional[str] = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date <= self.start_date:
            raise ValueError('End date must be after start date')
        return self

class QuotationUpdate(BaseModel):
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
    
    terms_and_conditions: Optional[str] = None
    admin_notes: Optional[str] = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError('End date must be after start date')
        return self

# ─── DASHBOARD OUTPUT SCHEMA ────────────────────────────────────────────────

class QuotationOut(BaseModel):
    id: int
    tenant_id: int
    client_id: int
    vehicle_id: int
    
    # Trip Details
    start_date: datetime
    end_date: datetime
    pickup_location: Optional[str] = None
    return_location: Optional[str] = None
    destination: Optional[str] = None
    
    # Financials
    daily_rate: Decimal
    total_amount: Decimal
    currency_code: str
    
    # Terms
    terms_and_conditions: Optional[str] = None
    admin_notes: Optional[str] = None
    
    # Status & Lifecycle
    status: QuotationStatus
    share_token: Optional[str] = None
    share_token_expires_at: Optional[datetime] = None
    booking_id: Optional[int] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    # Joined Data (Optional, populated by router if needed for Data Tables)
    client_name: Optional[str] = None
    vehicle_details: Optional[str] = None

    model_config = {"from_attributes": True}

# ─── PUBLIC PORTAL SCHEMA ───────────────────────────────────────────────────

class QuotationPublicView(BaseModel):
    """What the client sees when they open the share link."""
    id: int
    tenant_name: str
    client_name: str
    vehicle_details: str
    
    # Trip Details
    start_date: str
    end_date: str
    pickup_location: Optional[str] = None
    return_location: Optional[str] = None
    destination: Optional[str] = None
    
    # Financials
    daily_rate: str
    total_amount: str
    currency_code: str
    
    # Terms (Crucial for the public portal UI)
    terms_and_conditions: Optional[str] = None
    
    # Status & Expiry
    status: str
    expires_at: Optional[str] = None

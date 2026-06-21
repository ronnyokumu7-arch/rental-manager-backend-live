from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.models.clients import ClientStatus


class ClientBase(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=200)
    email: Optional[EmailStr] = None
    phone: str = Field(..., min_length=7, max_length=20)
    id_number: Optional[str] = Field(default=None, max_length=50)
    dl_number: Optional[str] = Field(default=None, max_length=50)
    residential_address: Optional[str] = None
    work_address: Optional[str] = None
    next_of_kin_name: Optional[str] = Field(default=None, max_length=200)
    next_of_kin_phone: Optional[str] = Field(default=None, max_length=20)


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, min_length=7, max_length=20)
    id_number: Optional[str] = Field(default=None, max_length=50)
    dl_number: Optional[str] = Field(default=None, max_length=50)
    residential_address: Optional[str] = None
    work_address: Optional[str] = None
    next_of_kin_name: Optional[str] = Field(default=None, max_length=200)
    next_of_kin_phone: Optional[str] = Field(default=None, max_length=20)
    status: Optional[ClientStatus] = None


class ClientOut(BaseModel):
    id: int
    tenant_id: int
    full_name: str
    email: Optional[EmailStr] = None
    phone: str
    id_number: Optional[str] = None
    dl_number: Optional[str] = None              # ADDED
    status: ClientStatus
    residential_address: Optional[str] = None
    work_address: Optional[str] = None
    next_of_kin_name: Optional[str] = None
    next_of_kin_phone: Optional[str] = None
    avatar_image: Optional[str] = None           # ADDED
    id_image_front: Optional[str] = None         # ADDED
    id_image_back: Optional[str] = None          # ADDED
    dl_image_front: Optional[str] = None         # ADDED
    is_archived: bool = False                    # ADDED
    archived_at: Optional[datetime] = None       # ADDED
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
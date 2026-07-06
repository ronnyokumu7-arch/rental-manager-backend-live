from typing import List
from pydantic import BaseModel, field_validator
from app.core.permissions import ALL_PERMISSION_KEYS

class RoleTemplateOut(BaseModel):
    id: int
    tenant_id: int
    job_title: str
    permissions: List[str]

    model_config = {"from_attributes": True}

class RoleTemplateUpdate(BaseModel):
    permissions: List[str]

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, v: List[str]):
        for perm in v:
            if perm not in ALL_PERMISSION_KEYS:
                raise ValueError(f"Invalid permission key: {perm}")
        return v

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.tenant_profile import TenantProfile
from app.models.users import User, UserRole
from app.schemas.tenant_profile import TenantProfileCreate, TenantProfileOut, TenantProfileUpdate


router = APIRouter(prefix="/tenant-profile", tags=["tenant-profile"])

tenant_admin_only = Depends(require_role([UserRole.tenant_admin, UserRole.super_admin]))


def _get_target_tenant_id(user: User, tenant_id: Optional[int] = None) -> int:
    """Resolves target tenant_id based on user role and parameter input."""
    if user.role == UserRole.super_admin:
        if tenant_id:
            return tenant_id
        if user.tenant_id:
            return user.tenant_id
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Super Admins must specify a tenant_id parameter."
        )
    return user.tenant_id


def _get_authorized_tenant_profile(user: User, db: Session, target_tenant_id: int) -> TenantProfile:
    profile = db.query(TenantProfile).filter(
        TenantProfile.tenant_id == target_tenant_id
    ).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not set up yet"
        )
    return profile


@router.get("/", response_model=TenantProfileOut)
def get_profile(
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_id = _get_target_tenant_id(current_user, tenant_id)
    return _get_authorized_tenant_profile(current_user, db, target_id)


@router.post("/", response_model=TenantProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: TenantProfileCreate,
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = tenant_admin_only,
):
    target_id = _get_target_tenant_id(current_user, tenant_id)
    
    existing = db.query(TenantProfile).filter(
        TenantProfile.tenant_id == target_id,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile already exists. Use PATCH to update.",
        )
        
    contract_prefix = f"T{target_id}"
    profile = TenantProfile(
        **payload.model_dump(),
        tenant_id=target_id,
        contract_prefix=contract_prefix,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.patch("/", response_model=TenantProfileOut)
def update_profile(
    payload: TenantProfileUpdate,
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = tenant_admin_only,
):
    target_id = _get_target_tenant_id(current_user, tenant_id)
    profile = _get_authorized_tenant_profile(current_user, db, target_id)
        
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
            
    db.commit()
    db.refresh(profile)
    return profile

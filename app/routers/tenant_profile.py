# app/api/routes/tenant_profile.py
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

# Allow both Tenant Admins (self-service) and Super Admins (management)
tenant_admin_or_super = Depends(require_role([UserRole.tenant_admin, UserRole.super_admin]))


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


def _clean_string(value: str | None) -> str | None:
    """Helper to sanitize inputs before DB insertion."""
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    return value


@router.get("/", response_model=TenantProfileOut)
def get_profile(
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_id = _get_target_tenant_id(current_user, tenant_id)
    
    profile = db.query(TenantProfile).filter(
        TenantProfile.tenant_id == target_id
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant profile has not been set up yet."
        )
    return profile


@router.post("/", response_model=TenantProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: TenantProfileCreate,
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = tenant_admin_or_super,
):
    target_id = _get_target_tenant_id(current_user, tenant_id)
    
    # Prevent duplicate profiles
    existing = db.query(TenantProfile).filter(
        TenantProfile.tenant_id == target_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profile already exists for this tenant. Use PATCH to update.",
        )
        
    # Generate consistent contract prefix
    contract_prefix = f"T{target_id:04d}"
    
    # Map Pydantic fields to DB columns explicitly to avoid alias issues
    profile = TenantProfile(
        tenant_id=target_id,
        company_name=_clean_string(payload.company_name),
        address=_clean_string(payload.business_location), # Maps wizard.business_location -> DB.address
        phone=_clean_string(payload.phone),
        email=_clean_string(payload.email),
        website=_clean_string(payload.website),
        tax_number=payload.kra_pin.upper() if payload.kra_pin else None, # Maps wizard.kra_pin -> DB.tax_number
        logo_url=_clean_string(payload.logo_url),
        contract_prefix=contract_prefix,
        contract_footer=_clean_string(payload.contract_terms), # Maps wizard.contract_terms -> DB.contract_footer
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
    current_user: User = tenant_admin_or_super,
):
    target_id = _get_target_tenant_id(current_user, tenant_id)
    
    profile = db.query(TenantProfile).filter(
        TenantProfile.tenant_id == target_id
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. Please create one first."
        )
        
    # Update only provided fields
    update_data = payload.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        # Handle specific mappings for wizard-friendly names
        if field == "business_location":
            setattr(profile, "address", _clean_string(value))
        elif field == "kra_pin":
            setattr(profile, "tax_number", value.upper() if value else None)
        elif field == "contract_terms":
            setattr(profile, "contract_footer", _clean_string(value))
        else:
            # Direct mapping for standard fields
            if isinstance(value, str):
                setattr(profile, field, _clean_string(value))
            else:
                setattr(profile, field, value)
            
    db.commit()
    db.refresh(profile)
    return profile

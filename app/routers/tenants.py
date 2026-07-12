# app/api/routes/tenants.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import Optional

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.tenants import Tenant, SubscriptionStatus
from app.models.tenant_profile import TenantProfile
from app.models.users import User, UserRole
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantOut
from app.core.security import get_password_hash

router = APIRouter(prefix="/tenants", tags=["tenants"])
super_admin_only = Depends(require_role([UserRole.super_admin]))


def _clean_string(value: str | None) -> str | None:
    """Converts empty strings to None to prevent DB unique constraint crashes."""
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    return value


@router.post("/", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    # 1. Sanitize optional string inputs immediately
    phone_number = _clean_string(payload.phone_number)
    kra_pin = _clean_string(payload.kra_pin)
    business_location = _clean_string(payload.business_location)
    admin_phone = _clean_string(payload.admin_phone)
    stripe_customer_id = _clean_string(payload.stripe_customer_id)
    paypal_payer_id = _clean_string(payload.paypal_payer_id)

    # 2. Prevent duplicate email registration (Check BOTH tables)
    existing_tenant = db.query(Tenant).filter(Tenant.email == payload.email).first()
    if existing_tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A tenant with this primary email already exists."
        )

    existing_user = db.query(User).filter(User.email == payload.admin_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this admin email already exists. Please use a different email."
        )

    try:
        # 3. Create Core Tenant Record (with Denormalized Admin Snapshot)
        tenant = Tenant(
            name=payload.name.strip(),
            email=payload.email.strip(),
            phone_number=phone_number,
            
            # ✅ NEW: Save Admin Details directly to Tenant Table for fast lookups
            admin_name=(payload.admin_name or payload.name).strip(),
            admin_email=payload.admin_email.strip(),
            admin_phone=admin_phone or phone_number,
            
            plan=payload.plan or "free_trial",
            subscription_status=SubscriptionStatus.trial,
            default_payment_method=payload.default_payment_method,
            stripe_customer_id=stripe_customer_id,
            paypal_payer_id=paypal_payer_id,
            payment_metadata=payload.payment_metadata or {},
            is_active=True,
            is_archived=False,
        )
        db.add(tenant)
        db.flush()  # Generates tenant.id without committing yet

        # 4. Auto-provision TenantProfile
        contract_prefix = f"T{tenant.id:04d}" 
        
        profile = TenantProfile(
            tenant_id=tenant.id,
            company_name=payload.name.strip(),
            address=business_location,
            phone=phone_number,
            email=payload.email.strip(),
            tax_number=kra_pin.upper() if kra_pin else None,
            contract_prefix=contract_prefix,
        )
        db.add(profile)

        # 5. Auto-provision Initial Tenant Admin User (For Auth)
        admin_user = User(
            email=payload.admin_email.strip(),
            full_name=(payload.admin_name or payload.name).strip(),
            phone_number=admin_phone or phone_number,
            hashed_password=get_password_hash(payload.password),
            role=UserRole.tenant_admin,
            tenant_id=tenant.id,
            is_active=True,
        )
        db.add(admin_user)

        db.commit()
        
        # ✅ CRITICAL FIX: Eagerly load profile so Pydantic can serialize it
        db.refresh(tenant)
        db.refresh(tenant.profile) 
        return tenant

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A database constraint was violated. This email or tax ID might already be registered."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to provision tenant environment: {str(e)}"
        )


@router.get("/", response_model=list[TenantOut])
def list_tenants(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None, description="Search by name or KRA PIN"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by ACTIVE or SUSPENDED"),
    show_archived: bool = Query(False, description="Include archived/vaulted tenants"),
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    # ✅ FIX: Use subquery for search to avoid row duplication from JOIN
    base_query = db.query(Tenant)
    
    if search:
        search_term = f"%{search}%"
        matching_ids = db.query(Tenant.id).join(TenantProfile).filter(
            (Tenant.name.ilike(search_term)) | 
            (TenantProfile.tax_number.ilike(search_term))
        ).subquery()
        base_query = base_query.filter(Tenant.id.in_(matching_ids))

    # Multi-tenancy & Vault Enforcement
    if not show_archived:
        base_query = base_query.filter(Tenant.is_archived == False)
        
    if status_filter == "ACTIVE":
        base_query = base_query.filter(Tenant.is_active == True)
    elif status_filter == "SUSPENDED":
        base_query = base_query.filter(Tenant.is_active == False)
        
    # ✅ FIX: Eager load profile to satisfy TenantOut schema
    query = base_query.options(joinedload(Tenant.profile)).offset(skip).limit(limit)
    
    tenants = query.all()
    return tenants


@router.patch("/{tenant_id}", response_model=TenantOut)
def update_tenant(
    tenant_id: int,
    payload: TenantUpdate,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    tenant = db.query(Tenant).options(joinedload(Tenant.profile)).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)

    try:
        db.commit()
        db.refresh(tenant)
        db.refresh(tenant.profile)
        return tenant
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Update failed due to a unique constraint violation."
        )


@router.post("/{tenant_id}/suspend", response_model=TenantOut)
def suspend_tenant(
    tenant_id: int,
    reason: Optional[str] = "Administrative Action",
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    tenant = db.query(Tenant).options(joinedload(Tenant.profile)).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    tenant.is_active = False
    db.commit()
    db.refresh(tenant)
    db.refresh(tenant.profile)
    return tenant


@router.post("/{tenant_id}/activate", response_model=TenantOut)
def activate_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    tenant = db.query(Tenant).options(joinedload(Tenant.profile)).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    tenant.is_active = True
    db.commit()
    db.refresh(tenant)
    db.refresh(tenant.profile)
    return tenant


@router.post("/{tenant_id}/archive", response_model=TenantOut)
def archive_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    """Moves tenant to Vault (Soft Delete)"""
    tenant = db.query(Tenant).options(joinedload(Tenant.profile)).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    tenant.is_archived = True
    tenant.is_active = False
    db.commit()
    db.refresh(tenant)
    db.refresh(tenant.profile)
    return tenant


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(
    tenant_id: int,
    hard_delete: bool = Query(False, description="Permanently remove from DB instead of archiving"),
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    if hard_delete:
        db.delete(tenant)
        db.commit()
    else:
        # Default behavior is soft delete / archive
        tenant.is_archived = True
        tenant.is_active = False
        db.commit()

# app/api/routes/tenants.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.tenants import Tenant, SubscriptionStatus
from app.models.tenant_profile import TenantProfile
from app.models.users import User, UserRole
from app.schemas.tenant import TenantCreate, TenantOut
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
    # 1. Sanitize all optional string inputs immediately
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

    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this admin email already exists. Please use a different email."
        )

    try:
        # 3. Create Core Tenant Record
        tenant = Tenant(
            name=payload.name.strip(),
            email=payload.email.strip(),
            phone_number=phone_number,
            plan=payload.plan or "free_trial",
            subscription_status=SubscriptionStatus.trial,
            default_payment_method=payload.default_payment_method,
            stripe_customer_id=stripe_customer_id,
            paypal_payer_id=paypal_payer_id,
            payment_metadata=payload.payment_metadata or {},
        )
        db.add(tenant)
        db.flush()  # Generates tenant.id without committing yet

        # 4. Auto-provision TenantProfile
        contract_prefix = f"T{tenant.id:04d}" 
        
        profile = TenantProfile(
            tenant_id=tenant.id,
            business_location=business_location,
            kra_pin=kra_pin.upper() if kra_pin else None,
            currency=payload.currency or "KES",
            time_zone=payload.time_zone or "Africa/Nairobi",
            is_corporate=payload.is_corporate,
            contract_prefix=contract_prefix,
        )
        db.add(profile)

        # 5. Auto-provision Initial Tenant Admin User
        # ✅ CRITICAL FIX: Uses the ACTUAL password from the frontend payload
        admin_user = User(
            email=payload.email.strip(),
            full_name=(payload.admin_name or payload.name).strip(),
            phone_number=admin_phone or phone_number,
            hashed_password=get_password_hash(payload.password),
            role=UserRole.tenant_admin,
            tenant_id=tenant.id,
            is_active=True,
        )
        db.add(admin_user)

        # Commit everything as a single atomic unit
        db.commit()
        db.refresh(tenant)
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
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    tenants = db.query(Tenant).offset(skip).limit(limit).all()
    return tenants

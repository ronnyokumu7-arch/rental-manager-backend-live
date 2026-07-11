from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.tenants import Tenant, SubscriptionStatus
from app.models.tenant_profile import TenantProfile
from app.models.users import User, UserRole
from app.schemas.tenant import TenantCreate, TenantOut
from app.core.security import get_password_hash # Adjust import path according to your auth utils

router = APIRouter(prefix="/tenants", tags=["tenants"])
super_admin_only = Depends(require_role([UserRole.super_admin]))


@router.post("/", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    # 1. Prevent duplicate email registration
    existing = db.query(Tenant).filter(Tenant.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A tenant with this primary email already exists."
        )

    try:
        # 2. Create Core Tenant Record
        tenant = Tenant(
            name=payload.name,
            email=payload.email,
            phone_number=payload.phone_number,
            plan=payload.plan,
            subscription_status=SubscriptionStatus.trial,
            default_payment_method=payload.default_payment_method,
            stripe_customer_id=payload.stripe_customer_id,
            paypal_payer_id=payload.paypal_payer_id,
            payment_metadata=payload.payment_metadata or {},
        )
        db.add(tenant)
        db.flush() # Flushes to generate tenant.id without committing transaction yet

        # 3. Auto-provision TenantProfile
        contract_prefix = f"T{tenant.id}"
        profile = TenantProfile(
            tenant_id=tenant.id,
            business_location=payload.business_location,
            kra_pin=payload.kra_pin,
            currency=payload.currency or "KES",
            time_zone=payload.time_zone or "Africa/Nairobi",
            is_corporate=payload.is_corporate,
            contract_prefix=contract_prefix,
        )
        db.add(profile)

        # 4. Auto-provision Initial Tenant Admin User
        temp_password = "ChangeMe123!" # Or generate a secure token / invitation link
        admin_user = User(
            email=payload.email,
            full_name=payload.admin_name or payload.name,
            phone_number=payload.admin_phone or payload.phone_number,
            hashed_password=get_password_hash(temp_password),
            role=UserRole.tenant_admin,
            tenant_id=tenant.id,
            is_active=True,
        )
        db.add(admin_user)

        # Commit everything as a single atomic unit
        db.commit()
        db.refresh(tenant)
        return tenant

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to provision tenant environment: {str(e)}"
        )

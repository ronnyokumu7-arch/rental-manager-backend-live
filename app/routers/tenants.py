from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.subscriptions import BillingCycle, PlanType, Subscription, SubscriptionStatus
from app.models.tenants import Tenant
from app.models.users import User, UserRole
from app.schemas.tenant import TenantCreate, TenantOut, TenantUpdate


router = APIRouter(prefix="/tenants", tags=["tenants"])

# Security Dependency
super_admin_only = Depends(require_role([UserRole.super_admin]))

TRIAL_DAYS = 30
GRACE_PERIOD_DAYS = 7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_tenant_or_404(tenant_id: int, db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return tenant


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    """
    Provision a new tenant. By default, assigns a free trial period, sets trial
    expiration, and initializes an accompanying Subscription record.
    """
    # 1. Check for duplicate email
    existing = db.query(Tenant).filter(Tenant.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A tenant with this email address already exists.",
        )

    now = datetime.now(timezone.utc)
    is_trial = payload.plan in ("free_trial", "starter_trial")

    if is_trial:
        trial_ends = now + timedelta(days=TRIAL_DAYS if payload.plan == "free_trial" else 14)
        sub_ends = trial_ends
        sub_status = SubscriptionStatus.trial if payload.plan == "free_trial" else SubscriptionStatus.starter_trial
    elif payload.plan == "pay_as_you_go":
        trial_ends = None
        sub_ends = None
        sub_status = SubscriptionStatus.active
    else:
        trial_ends = None
        sub_ends = now + timedelta(days=30)
        sub_status = SubscriptionStatus.active

    grace_ends = (sub_ends + timedelta(days=GRACE_PERIOD_DAYS)) if sub_ends else None

    # 2. Instantiate Tenant entity
    tenant = Tenant(
        name=payload.name,
        email=payload.email,
        phone_number=payload.phone_number,
        plan=payload.plan,
        subscription_status=sub_status,
        trial_ends_at=trial_ends,
        subscription_ends_at=sub_ends,
        grace_period_ends_at=grace_ends,
        default_payment_method=payload.default_payment_method,
        stripe_customer_id=payload.stripe_customer_id,
        paypal_payer_id=payload.paypal_payer_id,
        payment_metadata=payload.payment_metadata,
    )
    db.add(tenant)
    db.flush()  # Populates tenant.id for subscription mapping

    # 3. Create linked initial Subscription record
    try:
        plan_enum = PlanType(payload.plan)
    except ValueError:
        plan_enum = PlanType.free_trial

    billing_cycle = BillingCycle.trial if is_trial else (
        BillingCycle.pay_as_you_go if payload.plan == "pay_as_you_go" else BillingCycle.monthly
    )

    subscription = Subscription(
        tenant_id=tenant.id,
        plan=plan_enum,
        billing_cycle=billing_cycle,
        status=sub_status,
        starts_at=now,
        ends_at=sub_ends,
        grace_period_ends_at=grace_ends,
        auto_renew=True,
    )
    db.add(subscription)

    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/", response_model=list[TenantOut])
def list_tenants(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    return db.query(Tenant).offset(skip).limit(limit).all()


@router.get("/me", response_model=TenantOut)
def get_current_tenant(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any tenant agency.",
        )
    return _get_tenant_or_404(current_user.tenant_id, db)


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    return _get_tenant_or_404(tenant_id, db)


@router.patch("/{tenant_id}", response_model=TenantOut)
def update_tenant(
    tenant_id: int,
    payload: TenantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Tenant admins can update their own details; Super admin can update any
    if current_user.role != UserRole.super_admin and current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this tenant.",
        )

    tenant = _get_tenant_or_404(tenant_id, db)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)

    db.commit()
    db.refresh(tenant)
    return tenant


@router.post("/{tenant_id}/transition-to-payg", response_model=TenantOut)
def transition_tenant_to_pay_as_you_go(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    """
    Transitions a tenant (e.g. after trial expiration or admin action) onto 
    the pay_as_you_go plan, removing expiration dates and setting status to active.
    """
    tenant = _get_tenant_or_404(tenant_id, db)

    now = datetime.now(timezone.utc)
    tenant.plan = PlanType.pay_as_you_go.value
    tenant.subscription_status = SubscriptionStatus.active
    tenant.subscription_ends_at = None
    tenant.trial_ends_at = None
    tenant.grace_period_ends_at = None

    # Deactivate older subscriptions and add a PAYG subscription
    db.query(Subscription).filter(
        Subscription.tenant_id == tenant.id,
        Subscription.status.in_([SubscriptionStatus.trial, SubscriptionStatus.starter_trial, SubscriptionStatus.active]),
    ).update({"status": SubscriptionStatus.cancelled}, synchronize_session=False)

    payg_sub = Subscription(
        tenant_id=tenant.id,
        plan=PlanType.pay_as_you_go,
        billing_cycle=BillingCycle.pay_as_you_go,
        status=SubscriptionStatus.active,
        starts_at=now,
        ends_at=None,
        grace_period_ends_at=None,
        auto_renew=True,
    )
    db.add(payg_sub)

    db.commit()
    db.refresh(tenant)
    return tenant

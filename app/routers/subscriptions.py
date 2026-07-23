# app/routers/subscriptions.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.tenants import Tenant
from app.models.subscriptions import BillingCycle, PlanType, Subscription, SubscriptionStatus
from app.models.users import User, UserRole
from app.schemas.subscription import SubscriptionCreate, SubscriptionOut, SubscriptionUpdate

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

# The Bouncers
super_admin_only = Depends(require_role([UserRole.super_admin]))

PLAN_DURATIONS = {
    PlanType.free_trial: 30,
    PlanType.starter_trial: 14,
    PlanType.pay_as_you_go: None,  # Usage-driven / Indefinite
    PlanType.starter: None,
    PlanType.pro: None,
    PlanType.enterprise: None,
}

GRACE_PERIOD_DAYS = 7


# ---------------------------------------------------------------------------
# Business Logic Helpers
# ---------------------------------------------------------------------------

def _get_authorized_subscription(subscription_id: int, user: User, db: Session) -> Subscription:
    """Helper to retrieve subscription and enforce ownership/access control."""
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    
    # Super admins see all, regular users only their own
    if user.role != UserRole.super_admin and sub.tenant_id != user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own subscriptions",
        )
    return sub


def _compute_ends_at(plan: PlanType, billing_cycle: BillingCycle, starts_at: datetime) -> datetime | None:
    if plan == PlanType.free_trial:
        return starts_at + timedelta(days=30)
    if plan == PlanType.starter_trial:
        return starts_at + timedelta(days=14)
    if plan == PlanType.pay_as_you_go:
        return None  # Indefinite term
    if billing_cycle == BillingCycle.monthly:
        return starts_at + timedelta(days=30)
    if billing_cycle == BillingCycle.annual:
        return starts_at + timedelta(days=365)
    return None


# ---------------------------------------------------------------------------
# Request & Response Schemas (For Manual Provision)
# ---------------------------------------------------------------------------

class ManualProvisionRequest(BaseModel):
    tenant_id: int
    plan: str = Field(..., description="'starter', 'pro', or 'enterprise'")
    billing_cycle: str = Field(..., description="'monthly', 'annual', or 'pay_as_you_go'")
    payment_method: str = Field(..., description="'bank_transfer', 'mpesa_manual', 'cash', 'cheque'")
    reference_code: str = Field(..., description="External transaction or receipt reference code")
    amount_paid: Optional[float] = 0.0
    notes: Optional[str] = None
    custom_expiry_days: Optional[int] = None


# ---------------------------------------------------------------------------
# Routes - Tenant Facing
# ---------------------------------------------------------------------------

@router.get("/my", response_model=list[SubscriptionOut])
def get_my_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's tenant subscriptions."""
    if current_user.tenant_id is None:
        return []
    return db.query(Subscription).filter(
        Subscription.tenant_id == current_user.tenant_id,
    ).order_by(Subscription.created_at.desc()).all()


@router.get("/", response_model=list[SubscriptionOut])
def list_subscriptions(
    tenant_id: int | None = None,
    status: SubscriptionStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    """List all subscriptions (Super Admin only)."""
    query = db.query(Subscription)
    if tenant_id is not None:
        query = query.filter(Subscription.tenant_id == tenant_id)
    if status is not None:
        query = query.filter(Subscription.status == status)
    return query.order_by(Subscription.created_at.desc()).all()


@router.post("/", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
def create_subscription(
    payload: SubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    """Create a new subscription (Super Admin only)."""
    tenant = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    now = datetime.now(timezone.utc)
    ends_at = _compute_ends_at(payload.plan, payload.billing_cycle, now)
    grace_period_ends_at = (ends_at + timedelta(days=GRACE_PERIOD_DAYS)) if ends_at else None

    sub_status = (
        SubscriptionStatus.trial if payload.plan == PlanType.free_trial
        else SubscriptionStatus.starter_trial if payload.plan == PlanType.starter_trial
        else SubscriptionStatus.active
    )

    db_sub = Subscription(
        tenant_id=payload.tenant_id,
        plan=payload.plan,
        billing_cycle=payload.billing_cycle,
        status=sub_status,
        starts_at=now,
        ends_at=ends_at,
        grace_period_ends_at=grace_period_ends_at,
        auto_renew=payload.auto_renew,
    )
    db.add(db_sub)

    tenant.plan = payload.plan.value
    tenant.subscription_status = sub_status
    tenant.trial_ends_at = ends_at if payload.plan in (PlanType.free_trial, PlanType.starter_trial) else None
    tenant.subscription_ends_at = ends_at
    tenant.grace_period_ends_at = grace_period_ends_at

    db.commit()
    db.refresh(db_sub)
    return db_sub


@router.get("/{subscription_id}", response_model=SubscriptionOut)
def get_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific subscription by ID."""
    return _get_authorized_subscription(subscription_id, current_user, db)


@router.patch("/{subscription_id}", response_model=SubscriptionOut)
def update_subscription(
    subscription_id: int,
    payload: SubscriptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), 
):
    """Update subscription (e.g., toggle auto_renew)."""
    sub = _get_authorized_subscription(subscription_id, current_user, db)
    
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sub, field, value)
    db.commit()
    db.refresh(sub)
    return sub


@router.post("/{subscription_id}/suspend", response_model=SubscriptionOut)
def suspend_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    """Suspend a subscription (Super Admin only)."""
    sub = _get_authorized_subscription(subscription_id, current_user, db)
    if sub.status == SubscriptionStatus.suspended:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription is already suspended",
        )
    sub.status = SubscriptionStatus.suspended
    tenant = db.query(Tenant).filter(Tenant.id == sub.tenant_id).first()
    if tenant:
        tenant.subscription_status = SubscriptionStatus.suspended
    db.commit()
    db.refresh(sub)
    return sub


@router.post("/{subscription_id}/reactivate", response_model=SubscriptionOut)
def reactivate_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    """Reactivate a suspended subscription (Super Admin only)."""
    sub = _get_authorized_subscription(subscription_id, current_user, db)
    if sub.status == SubscriptionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription is already active",
        )
    if sub.status == SubscriptionStatus.cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cancelled subscriptions cannot be reactivated. Create a new subscription instead.",
        )

    now = datetime.now(timezone.utc)
    new_ends_at = _compute_ends_at(sub.plan, sub.billing_cycle, now)
    new_grace = (new_ends_at + timedelta(days=GRACE_PERIOD_DAYS)) if new_ends_at else None

    sub.status = SubscriptionStatus.active
    sub.starts_at = now
    sub.ends_at = new_ends_at
    sub.grace_period_ends_at = new_grace

    tenant = db.query(Tenant).filter(Tenant.id == sub.tenant_id).first()
    if tenant:
        tenant.subscription_status = SubscriptionStatus.active
        tenant.subscription_ends_at = new_ends_at
        tenant.grace_period_ends_at = new_grace

    db.commit()
    db.refresh(sub)
    return sub


@router.post("/{subscription_id}/cancel", response_model=SubscriptionOut)
def cancel_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    """Cancel a subscription (Super Admin only)."""
    sub = _get_authorized_subscription(subscription_id, current_user, db)
    if sub.status == SubscriptionStatus.cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription is already cancelled",
        )
    sub.status = SubscriptionStatus.cancelled
    tenant = db.query(Tenant).filter(Tenant.id == sub.tenant_id).first()
    if tenant:
        tenant.subscription_status = SubscriptionStatus.cancelled
    db.commit()
    db.refresh(sub)
    return sub


# ---------------------------------------------------------------------------
# Routes - Super Admin Manual Provisioning
# ---------------------------------------------------------------------------

@router.post("/admin/manual-activate", response_model=SubscriptionOut)
async def superadmin_manual_provision(
    payload: ManualProvisionRequest,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    """
    Super Admin Endpoint: Manually provisions or upgrades a tenant's subscription tier
    after verifying offline/bank payments.
    """
    clean_plan = payload.plan.lower().strip()
    if clean_plan == "professional":
        clean_plan = "pro"

    if clean_plan not in ["starter", "pro", "enterprise", "pay_as_you_go"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid plan. Must be 'starter', 'pro', 'enterprise', or 'pay_as_you_go'."
        )

    clean_cycle = payload.billing_cycle.lower().strip()
    if clean_cycle not in ["monthly", "annual", "pay_as_you_go"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid billing cycle. Must be 'monthly', 'annual', or 'pay_as_you_go'."
        )

    now = datetime.now(timezone.utc)
    if payload.custom_expiry_days and payload.custom_expiry_days > 0:
        duration_days = payload.custom_expiry_days
    else:
        duration_days = 365 if clean_cycle == "annual" else 30

    ends_at = now + timedelta(days=duration_days)

    sub = (
        db.query(Subscription)
        .filter(Subscription.tenant_id == payload.tenant_id)
        .order_by(Subscription.created_at.desc())
        .first()
    )

    if sub:
        sub.plan = clean_plan
        sub.billing_cycle = clean_cycle
        sub.status = SubscriptionStatus.active
        sub.starts_at = now
        sub.ends_at = ends_at
        sub.auto_renew = True
        sub.updated_at = now
    else:
        sub = Subscription(
            tenant_id=payload.tenant_id,
            plan=clean_plan,
            billing_cycle=clean_cycle,
            status=SubscriptionStatus.active,
            starts_at=now,
            ends_at=ends_at,
            auto_renew=True,
            created_at=now,
            updated_at=now,
        )
        db.add(sub)

    # Sync tenant-level settings
    tenant = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first()
    if tenant:
        if hasattr(tenant, "plan"):
            tenant.plan = clean_plan
        if hasattr(tenant, "billing_cycle"):
            tenant.billing_cycle = clean_cycle

    db.commit()
    db.refresh(sub)
    return sub

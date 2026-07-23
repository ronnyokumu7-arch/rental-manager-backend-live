# app/routers/payment_verifications.py
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.payments import PaymentVerification, VerificationStatus
from app.models.subscriptions import Subscription, PlanType, BillingCycle, SubscriptionStatus
from app.models.tenants import Tenant
from app.models.users import User, UserRole
from app.schemas.payment import (
    PaymentVerificationCreate,
    PaymentVerificationOut,
    PaymentVerificationReview,
)

router = APIRouter(prefix="/payment-verifications", tags=["payment-verifications"])

# The Bouncer
super_admin_only = Depends(require_role([UserRole.super_admin]))


@router.post("/", response_model=PaymentVerificationOut, status_code=status.HTTP_201_CREATED)
async def submit_payment_verification(
    payload: PaymentVerificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Tenant submits payment proof/reference code (M-Pesa, Bank Transfer, etc.) for admin verification.
    """
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User context is missing a tenant ID.",
        )

    # Check for duplicate reference code
    existing = (
        db.query(PaymentVerification)
        .filter(PaymentVerification.reference_code == payload.reference_code.strip())
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A payment verification request with this reference code already exists.",
        )

    verification = PaymentVerification(
        tenant_id=current_user.tenant_id,
        target_plan=payload.target_plan,
        target_billing_cycle=payload.target_billing_cycle,
        payment_method=payload.payment_method,
        reference_code=payload.reference_code.strip(),
        notes=payload.notes,
        status=VerificationStatus.pending,
    )
    db.add(verification)

    # ✅ NEW: Update the tenant's Subscription status to 'pending_verification'
    now = datetime.now(timezone.utc)
    current_sub = (
        db.query(Subscription)
        .filter(Subscription.tenant_id == current_user.tenant_id)
        .order_by(Subscription.created_at.desc())
        .first()
    )

    if current_sub:
        # Update existing subscription to pending
        current_sub.status = SubscriptionStatus.pending_verification
        current_sub.updated_at = now
    else:
        # Fallback: Create a pending subscription if none exists (shouldn't happen if onboarding is correct)
        try:
            plan_enum = PlanType(payload.target_plan)
        except ValueError:
            plan_enum = PlanType.starter
            
        try:
            cycle_enum = BillingCycle(payload.target_billing_cycle)
        except ValueError:
            cycle_enum = BillingCycle.monthly

        new_sub = Subscription(
            tenant_id=current_user.tenant_id,
            plan=plan_enum,
            billing_cycle=cycle_enum,
            status=SubscriptionStatus.pending_verification,
            starts_at=now,
            auto_renew=True,
            created_at=now,
            updated_at=now,
        )
        db.add(new_sub)

    db.commit()
    db.refresh(verification)
    return verification


@router.get("/", response_model=List[PaymentVerificationOut])
async def list_payment_verifications(
    status_filter: Optional[VerificationStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch verifications. Superadmins see all; regular tenant users see only their own tenant's requests.
    """
    is_superadmin = current_user.role == UserRole.super_admin

    query = db.query(PaymentVerification)

    if not is_superadmin:
        query = query.filter(PaymentVerification.tenant_id == current_user.tenant_id)

    if status_filter:
        query = query.filter(PaymentVerification.status == status_filter)

    # ✅ Load tenant relationship
    query = query.options(joinedload(PaymentVerification.tenant))
    
    results = query.order_by(PaymentVerification.created_at.desc()).all()
    
    # ✅ Manually populate tenant_name for each result
    # Pydantic will automatically include it in the response
    for verification in results:
        verification.tenant_name = verification.tenant.name if verification.tenant else f"Tenant #{verification.tenant_id}"

    return results


@router.patch("/{verification_id}/review", response_model=PaymentVerificationOut)
async def review_payment_verification(
    verification_id: int,
    payload: PaymentVerificationReview,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    """
    Superadmin Endpoint: Approve or reject a payment verification submission.
    Upon approval, updates both the tenant record and subscription details.
    """
    verification = (
        db.query(PaymentVerification)
        .filter(PaymentVerification.id == verification_id)
        .first()
    )
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment verification request not found.",
        )

    now = datetime.now(timezone.utc)
    verification.status = payload.status
    verification.reviewed_by_id = current_user.id
    verification.reviewed_at = now

    if payload.status == VerificationStatus.rejected:
        verification.rejection_reason = payload.rejection_reason
        # Optional: If rejected, we could revert the subscription status back to trial.
        # For now, we leave it as pending_verification so the tenant can try again.
    elif payload.status == VerificationStatus.approved:
        # 1. Update Tenant plan & billing cycle
        tenant = db.query(Tenant).filter(Tenant.id == verification.tenant_id).first()
        if tenant:
            if hasattr(tenant, "plan"):
                tenant.plan = verification.target_plan
            if hasattr(tenant, "billing_cycle"):
                tenant.billing_cycle = verification.target_billing_cycle

        # 2. Activate or update active subscription
        duration_days = 365 if verification.target_billing_cycle == "annual" else 30
        ends_at = now + timedelta(days=duration_days)

        sub = (
            db.query(Subscription)
            .filter(Subscription.tenant_id == verification.tenant_id)
            .order_by(Subscription.created_at.desc())
            .first()
        )

        if sub:
            sub.plan = verification.target_plan
            sub.billing_cycle = verification.target_billing_cycle
            sub.status = SubscriptionStatus.active  # ✅ Jumps to active
            sub.starts_at = now
            sub.ends_at = ends_at
            sub.auto_renew = True
            sub.updated_at = now
        else:
            # Fallback if subscription was somehow deleted
            sub = Subscription(
                tenant_id=verification.tenant_id,
                plan=verification.target_plan,
                billing_cycle=verification.target_billing_cycle,
                status=SubscriptionStatus.active,
                starts_at=now,
                ends_at=ends_at,
                auto_renew=True,
                created_at=now,
                updated_at=now,
            )
            db.add(sub)

    db.commit()
    db.refresh(verification)
    return verification

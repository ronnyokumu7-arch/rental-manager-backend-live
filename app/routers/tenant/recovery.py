# app/routers/tenants/recovery.py
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.tenants import Tenant
from app.models.users import User, UserRole
from app.schemas.tenant_recovery import (
    ChangeAdminEmailPayload,
    SendResetLinkPayload,
    AdminRecoveryOptionsOut,
    VerificationMethod,
)
from app.services.email import send_admin_recovery_notification, send_sms_otp

router = APIRouter()

super_admin_only = Depends(require_role([UserRole.super_admin]))


def _mask_email(email: str) -> str:
    """Masks email for safe display (e.g., j***@example.com)."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    masked_local = local[0] + "***" if len(local) > 1 else "***"
    return f"{masked_local}@{domain}"


def _mask_phone(phone: str | None) -> str | None:
    """Masks phone for safe display (e.g., +254 *** *** 7890)."""
    if not phone or len(phone) < 10:
        return None
    return f"{phone[:-7]} *** *** {phone[-4:]}"


@router.get("/{tenant_id}/admin-recovery-options", response_model=AdminRecoveryOptionsOut)
def get_recovery_options(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Calculate rate limits
    now = datetime.utcnow()
    reset_attempts_remaining = 3
    cooldown_minutes = 0

    if tenant.last_reset_request_at:
        minutes_since = (now - tenant.last_reset_request_at).total_seconds() / 60
        if minutes_since < 60:
            reset_attempts_remaining = max(0, 3 - int(minutes_since / 20))
        if minutes_since < 15:
            cooldown_minutes = int(15 - minutes_since)

    return AdminRecoveryOptionsOut(
        admin_email_masked=_mask_email(tenant.admin_email),
        admin_phone_masked=_mask_phone(tenant.admin_phone),
        phone_verified=False,  # TODO: Add phone_verified field to Tenant model
        reset_attempts_remaining=reset_attempts_remaining,
        email_change_cooldown_minutes=cooldown_minutes,
        last_reset_request_at=tenant.last_reset_request_at.isoformat() if tenant.last_reset_request_at else None,
    )


@router.post("/{tenant_id}/send-reset-link", status_code=status.HTTP_200_OK)
def send_reset_link(
    tenant_id: int,
    payload: SendResetLinkPayload,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Rate limit check
    if tenant.last_reset_request_at:
        minutes_since = (datetime.utcnow() - tenant.last_reset_request_at).total_seconds() / 60
        if minutes_since < 15:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {int(15 - minutes_since)} minutes before requesting another reset link.",
            )

    # Update timestamp
    tenant.last_reset_request_at = datetime.utcnow()
    db.commit()

    # Trigger notifications
    if payload.send_to_email:
    send_admin_recovery_notification(
        to=tenant.admin_email,
        full_name=tenant.admin_name,
        subject="Password Reset Requested",
        custom_message=payload.custom_message or "A password reset has been requested for your account. Please check your email for the reset link.",
    )

    if payload.send_to_phone and tenant.admin_phone:
        send_sms_otp(
            phone=tenant.admin_phone,
            message=f"Password reset requested for {tenant.name}. Check your email for the reset link.",
        )

    return {"message": "Reset instructions sent successfully."}


@router.post("/{tenant_id}/change-admin-email", status_code=status.HTTP_200_OK)
def change_admin_email(
    tenant_id: int,
    payload: ChangeAdminEmailPayload,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Enforce cooldown
    if tenant.email_change_cooldown_until and datetime.utcnow() < tenant.email_change_cooldown_until:
        remaining = int((tenant.email_change_cooldown_until - datetime.utcnow()).total_seconds() / 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Email change cooldown active. Wait {remaining} minutes.",
        )

    # Validate OTP for non-manual methods
    if payload.verification_method != VerificationMethod.manual_override:
        if not payload.otp or len(payload.otp) != 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Valid 6-digit OTP is required for email/phone verification.",
            )
        # TODO: Verify OTP against stored value before proceeding

    # Check new email uniqueness
    existing_user = db.query(User).filter(User.email == payload.new_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already registered to another user.",
        )

    old_email = tenant.admin_email
    old_phone = tenant.admin_phone

    # Apply change
    tenant.admin_email = payload.new_email.strip()
    tenant.admin_email_changed_at = datetime.utcnow()
    tenant.admin_changed_by_user_id = current_user.id
    tenant.email_change_cooldown_until = datetime.utcnow() + timedelta(hours=24)

    # Notify old contact channel
    if payload.verification_method == VerificationMethod.email and old_email:
    send_admin_recovery_notification(
        to=old_email,
        full_name=tenant.admin_name,
        subject="Admin Email Changed",
        custom_message=(
            f"Your admin email was changed to {payload.new_email} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} "
            f"by Super Admin {current_user.full_name}. If this wasn't authorized, contact support immediately."
        ),
    )
    elif payload.verification_method == VerificationMethod.phone and old_phone:
        send_sms_otp(
            phone=old_phone,
            message=(
                f"ALERT: Your admin email was changed to {payload.new_email}. "
                f"If unauthorized, contact support immediately."
            ),
        )

    db.commit()

    return {
        "message": "Admin email updated successfully.",
        "new_email": payload.new_email,
        "notification_sent_to": old_email if payload.verification_method == VerificationMethod.email else old_phone,
    }

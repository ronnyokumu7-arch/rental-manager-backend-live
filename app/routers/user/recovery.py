# app/routers/users/recovery.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.users import User, UserRole
from app.schemas.tenant_recovery import SendResetLinkPayload
from app.services.email import send_admin_recovery_notification, send_sms_otp
from ._helpers import _get_user_or_404

router = APIRouter()

admin_or_above = Depends(require_role([UserRole.super_admin, UserRole.tenant_admin]))

def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[0]}***@{domain}" if len(local) > 1 else "***@{domain}"

def _mask_phone(phone: str | None) -> str | None:
    if not phone or len(phone) < 10:
        return None
    return f"{phone[:-7]} *** *** {phone[-4:]}"

@router.get("/{user_id}/recovery-options")
def get_user_recovery_options(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = admin_or_above,
):
    user = _get_user_or_404(user_id, db)
    
    # Basic permission check for viewing recovery options
    if current_user.role == UserRole.tenant_admin and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return {
        "email_masked": _mask_email(user.email),
        "phone_masked": _mask_phone(user.phone_number),
        "phone_verified": getattr(user, "phone_verified", False),
        "two_factor_enabled": user.two_factor_enabled,
        "account_locked_until": user.account_locked_until.isoformat() if getattr(user, "account_locked_until", None) else None,
    }

@router.post("/{user_id}/send-reset-link", status_code=status.HTTP_200_OK)
def send_user_reset_link(
    user_id: int,
    payload: SendResetLinkPayload,
    db: Session = Depends(get_db),
    current_user: User = admin_or_above,
):
    user = _get_user_or_404(user_id, db)
    
    if current_user.role == UserRole.tenant_admin and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if payload.send_to_email:
    send_admin_recovery_notification(
        to=user.email,
        full_name=user.full_name,
        subject="Password Reset Requested",
        custom_message=payload.custom_message or "A password reset has been requested for your account.",
    )

    if payload.send_to_phone and user.phone_number:
        send_sms_otp(
            phone=user.phone_number,
            message=f"Password reset requested for your account at {user.tenant_id}. Check your email for instructions.",
        )

    return {"message": "Reset instructions sent successfully."}

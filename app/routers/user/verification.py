# app/routers/user/verification.py
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Literal
from pydantic import BaseModel

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.users import User, UserRole
from app.schemas.user import UserOut
from app.services.email import send_verification_email
from ._helpers import _get_user_or_404, _enforce_staff_permission

router = APIRouter()

admin_or_above = Depends(require_role([UserRole.super_admin, UserRole.tenant_admin]))

# ---------------------------------------------------------------------------
# Payload Schemas
# ---------------------------------------------------------------------------
class VerificationPayload(BaseModel):
    channel: Literal["email", "phone"]

class VerifyTokenPayload(BaseModel):
    token: str
    channel: Literal["email", "phone"]

# ---------------------------------------------------------------------------
# 1. SEND VERIFICATION (Automated Flow)
# ---------------------------------------------------------------------------
@router.post("/{user_id}/send-verification", status_code=status.HTTP_200_OK)
def send_verification(
    user_id: int,
    payload: VerificationPayload,
    db: Session = Depends(get_db),
    current_user: User = admin_or_above,
):
    """
    Triggers an automated verification email or generates a shareable message.
    """
    user = _get_user_or_404(user_id, db)
    
    # ✅ FIXED: Added 'db' as the 4th argument to prevent 500 crash
    _enforce_staff_permission(current_user, user, "verify", db)

    if payload.channel == "email" and user.email_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is already verified.")
    if payload.channel == "phone" and user.phone_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone is already verified.")

    if payload.channel == "email" and not user.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User has no email address on file.")
    if payload.channel == "phone" and not user.phone_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User has no phone number on file.")

    # --- Generate Secure Verification Token ---
    verification_token = secrets.token_urlsafe(32)
    user.invite_token = verification_token
    user.invite_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    db.commit()

    # ✅ Use localhost for local development testing (easily swappable for env var later)
    frontend_url = "http://localhost:3000"
    
    # ✅ Include channel in the URL so the frontend knows what to verify
    verification_link = f"{frontend_url}/verify?token={verification_token}&channel={payload.channel}"

    # --- Service Integration ---
    if payload.channel == "email":
        success = send_verification_email(
            to=user.email,
            full_name=user.full_name,
            verification_link=verification_link
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Failed to send email. Please check Resend API key and server logs."
            )
        return {"message": f"Verification email sent successfully to {user.email}."}
        
    else:
        # ✅ Return a clean link and a pre-formatted message for the admin to copy
        shareable_message = f"Hello {user.full_name}, please verify your phone number for Rental Manager by clicking this secure link: {verification_link}"
        
        return {
            "message": "Phone verification link generated successfully.",
            "verification_link": verification_link,
            "shareable_message": shareable_message
        }


# ---------------------------------------------------------------------------
# 2. VERIFY TOKEN (Public Endpoint - No Auth Required)
# ---------------------------------------------------------------------------
@router.post("/verify", response_model=UserOut)
def verify_token(
    payload: VerifyTokenPayload,
    db: Session = Depends(get_db),
):
    """
    Public endpoint called by the user clicking the link in their email or WhatsApp.
    """
    # 1. Find user by token
    user = db.query(User).filter(User.invite_token == payload.token).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired verification link.")

    # 2. Check expiration
    if user.invite_expires_at and user.invite_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification link has expired. Please request a new one from your administrator.")

    # 3. Apply verification based on channel
    if payload.channel == "email":
        if user.email_verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is already verified.")
        user.email_verified = True
    elif payload.channel == "phone":
        if user.phone_verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone is already verified.")
        user.phone_verified = True

    # 4. Invalidate the token so it can't be reused
    user.invite_token = None
    user.invite_expires_at = None
    
    db.commit()
    db.refresh(user)
    
    return user


# ---------------------------------------------------------------------------
# 3. MARK VERIFIED (Manual Admin Override - Shield Button)
# ---------------------------------------------------------------------------
@router.post("/{user_id}/mark-verified", response_model=UserOut)
def mark_verified(
    user_id: int,
    payload: VerificationPayload,
    db: Session = Depends(get_db),
    current_user: User = admin_or_above,
):
    """
    Allows an admin to manually mark a user's email or phone as verified.
    """
    user = _get_user_or_404(user_id, db)
    
    # ✅ FIXED: Added 'db' as the 4th argument to prevent 500 crash
    _enforce_staff_permission(current_user, user, "verify", db)

    if payload.channel == "email":
        user.email_verified = True
    elif payload.channel == "phone":
        user.phone_verified = True
        
    db.commit()
    db.refresh(user)
    
    return user

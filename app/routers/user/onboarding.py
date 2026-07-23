# app/routers/users/onboarding.py
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.users import User
from app.schemas.user import UserOut, AcceptInvitePayload
from app.core.security import get_password_hash

router = APIRouter()

@router.post("/accept-invite", response_model=UserOut)
def accept_invite(
    payload: AcceptInvitePayload,
    db: Session = Depends(get_db),
):
    """
    Allows a user to accept an invite by providing their token and setting a password.
    This flips is_onboarded to True and clears the invite token.
    """
    # 1. Find user by token
    user = db.query(User).filter(User.invite_token == payload.invite_token).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invite token")

    # 2. Check expiration
    if user.invite_expires_at and user.invite_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite token has expired")

    # 3. Check if already onboarded
    if user.is_onboarded:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already active")

    # 4. Conditional Validation for Drivers
    if user.job_title == "Driver":
        if not payload.dl_number:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver's License Number is required for Drivers.")
        if not payload.dl_image_url:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver's License Image is required for Drivers.")

    # 5. Map Identity & Compliance Fields
    user.full_name = payload.full_name
    user.email = payload.email
    user.phone_number = payload.phone_number
    user.avatar_url = payload.avatar_url
    
    user.id_number = payload.id_number
    user.id_image_url = payload.id_image_url
    user.dl_number = payload.dl_number
    user.dl_image_url = payload.dl_image_url
    user.dl_expiry = payload.dl_expiry

    # 6. Update user state (Password & Onboarding Status)
    user.password_hash = get_password_hash(payload.password)
    user.is_onboarded = True
    # ✅ REMOVED: user.email_verified = True. 
    # Users now land in the "Verify" state, awaiting admin to trigger email/phone verification.
    user.invite_token = None    # Invalidate the token so it can't be reused
    user.invite_expires_at = None
    
    db.commit()
    db.refresh(user)
    return user

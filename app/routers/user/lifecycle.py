# app/routers/users/lifecycle.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.users import User, UserRole
from app.schemas.user import UserOut
from ._helpers import _get_user_or_404, _enforce_staff_permission

router = APIRouter()

admin_or_above = Depends(require_role([UserRole.super_admin, UserRole.tenant_admin]))


@router.post("/{user_id}/suspend", response_model=UserOut)
def suspend_user(
    user_id: int,
    reason: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = admin_or_above,
):
    """Suspend a user and record the reason."""
    user = _get_user_or_404(user_id, db)
    
    if current_user.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot suspend yourself")
        
    _enforce_staff_permission(current_user, user, "suspend")
    
    if user.is_suspended:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already suspended")
        
    user.is_suspended = True
    user.suspension_reason = reason
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reactivate", response_model=UserOut)
def reactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = admin_or_above,
):
    """Reactivate a previously suspended user."""
    user = _get_user_or_404(user_id, db)
    
    _enforce_staff_permission(current_user, user, "reactivate")
    
    if not user.is_suspended:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not suspended")
        
    user.is_suspended = False
    user.suspension_reason = None
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = admin_or_above,
):
    """Permanently delete a user."""
    user = _get_user_or_404(user_id, db)
    
    if current_user.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account")
        
    _enforce_staff_permission(current_user, user, "delete")
    
    db.delete(user)
    db.commit()

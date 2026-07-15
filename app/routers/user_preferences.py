from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/user/preferences", tags=["user-preferences"])

@router.get("/", response_model=dict)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's UI preferences"""
    return {
        "theme": current_user.theme_preference or "system",
        "density": current_user.density_preference or "comfortable",
    }

@router.patch("/", response_model=UserOut)
def update_preferences(
    theme: str | None = None,
    density: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update current user's UI preferences"""
    if theme is not None:
        if theme not in ["light", "dark", "system"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid theme preference")
        current_user.theme_preference = theme
    
    if density is not None:
        if density not in ["comfortable", "compact"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid density preference")
        current_user.density_preference = density
    
    db.commit()
    db.refresh(current_user)
    return current_user

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.activity_log import ActivityLog
from app.models.users import User
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/activity-logs", tags=["activity_logs"])

class ActivityLogOut(BaseModel):
    id: int
    user_id: int
    action: str
    target_type: Optional[str]
    target_id: Optional[int]
    details: Optional[dict]
    created_at: datetime
    
    model_config = {"from_attributes": True}

@router.get("/", response_model=List[ActivityLogOut])
def get_activity_logs(
    user_id: Optional[int] = Query(None, description="Filter by specific user ID"),
    limit: int = Query(50, description="Number of logs to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get activity logs. 
    - If user_id is provided, returns logs for that user (Admin viewing staff).
    - If no user_id, returns logs for the current user (Staff viewing self).
    """
    query = db.query(ActivityLog)
    
    if user_id:
        # Security: Ensure admin can only view logs for users in their tenant (unless super_admin)
        if current_user.role.value != "super_admin":
            target_user = db.query(User).filter(User.id == user_id, User.tenant_id == current_user.tenant_id).first()
            if not target_user:
                raise HTTPException(status_code=403, detail="Access denied")
        
        query = query.filter(ActivityLog.user_id == user_id)
    else:
        # Default to current user
        query = query.filter(ActivityLog.user_id == current_user.id)
        
    return query.order_by(ActivityLog.created_at.desc()).limit(limit).all()

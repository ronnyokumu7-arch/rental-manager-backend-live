# app/routers/system.py
import os
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User, UserRole
from app.services.daily_scheduler import DailySchedulerService

router = APIRouter(prefix="/system", tags=["system"])

# Load the secret from environment variables (Fallback for local dev)
CRON_SECRET = os.getenv("CRON_SECRET", "super-secret-cron-key-change-me-in-production")

async def verify_system_access(
    x_cron_secret: str = Header(None, alias="X-Cron-Secret"),
    current_user: User = Depends(get_current_user)
):
    """
    DUAL-AUTH SECURITY:
    1. If triggered by a Cron Job, it must pass the X-Cron-Secret header.
    2. If triggered manually from the UI, the user MUST be a super_admin.
    """
    # Path A: Automated Cron Job
    if x_cron_secret == CRON_SECRET:
        return {"triggered_by": "cron_job"}
    
    # Path B: Manual Admin Trigger
    if current_user and current_user.role == UserRole.super_admin:
        return {"triggered_by": "super_admin", "user": current_user.full_name}
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, 
        detail="Not authorized. Requires Super Admin role or valid Cron Secret."
    )

@router.post("/run-daily-tasks")
def run_daily_tasks(
    access: dict = Depends(verify_system_access),
    db: Session = Depends(get_db)
):
    """
    Manually or automatically triggers the daily compliance and financial checks.
    """
    try:
        DailySchedulerService.run_daily_checks(db)
        return {
            "message": "Daily tasks generated successfully",
            "details": access
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Scheduler failed: {str(e)}"
        )

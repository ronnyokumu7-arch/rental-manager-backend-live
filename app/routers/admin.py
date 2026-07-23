from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.dependencies.auth import get_current_user
from app.db.database import get_db
from app.dependencies.rbac import require_role
from app.jobs.booking_jobs import run_booking_auto_archive
from app.jobs.subscription_jobs import run_subscription_lifecycle
from app.models.users import User, UserRole
# Adjust this import to match your actual Subscription model location
from app.models.subscriptions import Subscription 

router = APIRouter(prefix="/admin", tags=["admin"])

# Dependency for cleaner code
super_admin_only = Depends(require_role([UserRole.super_admin]))

# --- Subscription Endpoints ---

@router.get("/subscriptions/pending")
def get_pending_subscriptions(
    current_user: User = super_admin_only,
    db: Session = Depends(get_db)
):
    """
    Fetch all subscriptions awaiting approval.
    Matches path: /api/v1/admin/subscriptions/pending
    """
    try:
        # Replace 'Subscription' with your actual model name 
        # and 'status' with your actual column name
        pending = db.query(Subscription).filter(Subscription.status == "pending").all()
        return pending
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch subscriptions: {str(e)}")

# --- Job Trigger Endpoints ---

@router.post("/jobs/run-subscription-lifecycle")
def trigger_subscription_lifecycle(
    current_user: User = super_admin_only
):
    run_subscription_lifecycle()
    return {"message": "Subscription lifecycle job completed"}

@router.post("/jobs/run-booking-archive")
def trigger_booking_archive(
    current_user: User = super_admin_only
):
    run_booking_auto_archive()
    return {"message": "Booking auto-archive job completed"}

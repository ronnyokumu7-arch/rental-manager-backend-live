from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from sqlalchemy import func

from app.db.database import get_db
from app.dependencies.rbac import require_role
from app.models.users import User, UserRole
from app.models.bookings import Booking
from app.models.vehicles import Vehicle
from app.models.invoices import Invoice

router = APIRouter(prefix="/tenants", tags=["Agency Health"])

@router.get("/{tenant_id}/health")
def get_agency_health(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.super_admin]))
):
    now = datetime.utcnow()
    last_7_days = now - timedelta(days=7)
    last_30_days = now - timedelta(days=30)
    
    try:
        logins_7d = db.query(func.count(func.distinct(User.id))).filter(
            User.tenant_id == tenant_id,
            User.last_login_at >= last_7_days
        ).scalar() or 0

        logins_30d = db.query(func.count(func.distinct(User.id))).filter(
            User.tenant_id == tenant_id,
            User.last_login_at >= last_30_days
        ).scalar() or 0
        
        last_active = db.query(User.last_login_at).filter(
            User.tenant_id == tenant_id,
            User.last_login_at.isnot(None)
        ).order_by(User.last_login_at.desc()).first()
        last_active_at = last_active[0].isoformat() if last_active else None

        total_vehicles = db.query(func.count(Vehicle.id)).filter(
            Vehicle.tenant_id == tenant_id
        ).scalar() or 0
        
        active_vehicles = db.query(func.count(func.distinct(Booking.vehicle_id))).filter(
            Booking.tenant_id == tenant_id,
            Booking.start_date <= now,
            Booking.end_date >= now
        ).scalar() or 0
        
        utilization_pct = round((active_vehicles / total_vehicles * 100), 1) if total_vehicles > 0 else 0

        bookings_this_week = db.query(func.count(Booking.id)).filter(
            Booking.tenant_id == tenant_id,
            Booking.created_at >= last_7_days
        ).scalar() or 0
        
        bookings_last_week = db.query(func.count(Booking.id)).filter(
            Booking.tenant_id == tenant_id,
            Booking.created_at >= last_7_days - timedelta(days=7),
            Booking.created_at < last_7_days
        ).scalar() or 0

        total_paid = db.query(func.count(Invoice.id)).filter(
            Invoice.tenant_id == tenant_id,
            Invoice.status == 'paid'
        ).scalar() or 0
        
        overdue_count = db.query(func.count(Invoice.id)).filter(
            Invoice.tenant_id == tenant_id,
            Invoice.status == 'overdue',
            Invoice.due_date < now
        ).scalar() or 0
        
        on_time_rate = round(((total_paid - overdue_count) / total_paid * 100), 1) if total_paid > 0 else 100.0

        score = 0
        score += min(utilization_pct * 0.3, 30)          
        score += min(on_time_rate * 0.3, 30)             
        score += min((bookings_this_week / max(bookings_last_week, 1)) * 20, 20) 
        score += min((logins_7d / 7) * 2, 20) 
        
        risk_level = "low" if score >= 70 else "medium" if score >= 40 else "high"
        trend = "up" if bookings_this_week > bookings_last_week else "down" if bookings_this_week < bookings_last_week else "stable"

        return {
            "score": {
                "score": round(score),
                "riskLevel": risk_level,
                "trend": trend,
                "lastCalculatedAt": now.isoformat()
            },
            "activity": {
                "loginsLast7Days": logins_7d,
                "loginsLast30Days": logins_30d,
                "activeDaysThisMonth": 0,
                "lastActiveAt": last_active_at,
                "avgSessionDurationMinutes": 0
            },
            "utilization": {
                "totalVehicles": total_vehicles,
                "activeVehicles": active_vehicles,
                "utilizationPercentage": utilization_pct,
                "idleVehiclesCount": total_vehicles - active_vehicles
            },
            "revenueVelocity": {
                "bookingsThisWeek": bookings_this_week,
                "bookingsLastWeek": bookings_last_week,
                "bookingsThisMonth": 0,
                "trend": trend,
                "weeklyData": []
            },
            "paymentReliability": {
                "currentStreak": 0,
                "onTimePaymentRate": on_time_rate,
                "totalInvoicesPaid": total_paid,
                "overdueInvoicesCount": overdue_count
            },
            "featureAdoption": {
                "modulesUsed": [],
                "totalAvailableModules": 6,
                "adoptionPercentage": 0,
                "mostUsedModule": "bookings",
                "leastUsedModule": None
            },
            "supportTickets": {
                "openTickets": 0,
                "closedThisMonth": 0,
                "avgResolutionTimeHours": 0,
                "trend": "stable"
            }
        }
    except Exception as e:
        print(f"HEALTH ENDPOINT ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to calculate health metrics: {str(e)}")

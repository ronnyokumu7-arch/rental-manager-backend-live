# app/services/health_service.py
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models.tenants import Tenant
from app.models.users import User
from app.models.bookings import Booking # Assuming this exists
from app.models.vehicles import Vehicle   # Assuming this exists
from app.models.invoices import Invoice   # Assuming this exists
from app.models.support_tickets import SupportTicket # Assuming this exists

class HealthService:
    @staticmethod
    def get_agency_health(db: Session, tenant_id: int) -> dict:
        """
        Returns privacy-safe aggregate health metrics for a specific tenant.
        No PII, no specific booking/client details are exposed.
        """
        now = datetime.utcnow()
        last_7_days = now - timedelta(days=7)
        last_30_days = now - timedelta(days=30)
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 1. Activity Pulse (Aggregate Login Counts)
        login_counts = db.query(
            func.count(func.distinct(User.id)).filter(User.last_login_at >= last_7_days).label('logins_7d'),
            func.count(func.distinct(User.id)).filter(User.last_login_at >= last_30_days).label('logins_30d')
        ).filter(User.tenant_id == tenant_id).first()

        active_sessions = db.query(func.avg(User.avg_session_duration_minutes)).filter(
            User.tenant_id == tenant_id, 
            User.last_login_at >= last_30_days
        ).scalar() or 0

        # 2. Fleet Utilization (Asset Efficiency)
        total_vehicles = db.query(func.count(Vehicle.id)).filter(Vehicle.tenant_id == tenant_id).scalar() or 0
        active_vehicles = db.query(func.count(func.distinct(Booking.vehicle_id))).filter(
            Booking.tenant_id == tenant_id,
            Booking.start_date <= now,
            Booking.end_date >= now
        ).scalar() or 0
        
        utilization_pct = round((active_vehicles / total_vehicles * 100), 1) if total_vehicles > 0 else 0

        # 3. Revenue Velocity (Booking Momentum - Counts Only)
        bookings_this_week = db.query(func.count(Booking.id)).filter(
            Booking.tenant_id == tenant_id,
            Booking.created_at >= last_7_days
        ).scalar() or 0

        bookings_last_week = db.query(func.count(Booking.id)).filter(
            Booking.tenant_id == tenant_id,
            Booking.created_at >= last_7_days - timedelta(days=7),
            Booking.created_at < last_7_days
        ).scalar() or 0

        # 4. Payment Reliability (Financial Trust)
        total_paid = db.query(func.count(Invoice.id)).filter(
            Invoice.tenant_id == tenant_id,
            Invoice.status == 'paid'
        ).scalar() or 0

        overdue_count = db.query(func.count(Invoice.id)).filter(
            Invoice.tenant_id == tenant_id,
            Invoice.status == 'overdue',
            Invoice.due_date < now
        ).scalar() or 0

        on_time_rate = round(((total_paid - overdue_count) / total_paid * 100), 1) if total_paid > 0 else 100

        # 5. Composite Health Score Calculation (0-100)
        # Weighted algorithm based on platform priorities
        score = 0
        score += min(utilization_pct * 0.3, 30)          # 30% weight: Asset efficiency
        score += min(on_time_rate * 0.3, 30)             # 30% weight: Financial reliability  
        score += min((bookings_this_week / max(bookings_last_week, 1)) * 20, 20) # 20% weight: Growth momentum
        score += min((login_counts.logins_7d / 7) * 2, 20) # 20% weight: Platform engagement
        
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
                "loginsLast7Days": login_counts.logins_7d or 0,
                "loginsLast30Days": login_counts.logins_30d or 0,
                "activeDaysThisMonth": 0, # TODO: Implement distinct active days query
                "lastActiveAt": None,     # TODO: Get most recent user.last_login_at
                "avgSessionDurationMinutes": round(active_sessions, 1)
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
                "bookingsThisMonth": 0, # TODO: Add current month count
                "trend": trend,
                "weeklyData": [] # TODO: Implement 8-week historical array
            },
            "paymentReliability": {
                "currentStreak": 0, # TODO: Calculate consecutive on-time payments
                "onTimePaymentRate": on_time_rate,
                "totalInvoicesPaid": total_paid,
                "overdueInvoicesCount": overdue_count
            },
            "featureAdoption": {
                "modulesUsed": [],      # TODO: Track module access logs
                "totalAvailableModules": 6,
                "adoptionPercentage": 0,
                "mostUsedModule": "bookings",
                "leastUsedModule": None
            },
            "supportTickets": {
                "openTickets": 0,       # TODO: Query open tickets
                "closedThisMonth": 0,   # TODO: Query resolved tickets
                "avgResolutionTimeHours": 0, # TODO: Calculate avg resolution time
                "trend": "stable"
            }
        }

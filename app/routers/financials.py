# backend/app/routers/financials.py
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, and_, or_, extract, case
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.users import User
from app.models.invoices import Invoice, InvoiceStatus
from app.models.contracts import Contract, ContractStatus
from app.models.payments import Payment, PaymentStatus
from app.models.bookings import Booking
from app.schemas.financials import (
    FinancialOverviewOut, 
    RevenueOverview, 
    InvoiceStatusSummary, 
    ContractHealth,
    MonthlyRevenueItem,
    ActivityItem
)

router = APIRouter(prefix="/financials", tags=["financials"])

@router.get("/overview", response_model=FinancialOverviewOut)
def get_financial_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    tenant_id = current_user.tenant_id
    now = datetime.now(timezone.utc)

    # =====================================================
    # 1. REVENUE OVERVIEW
    # =====================================================
    
    # Total Revenue (sum of completed payments)
    total_revenue_result = db.query(func.sum(Payment.amount)).filter(
        Payment.tenant_id == tenant_id,
        Payment.status == PaymentStatus.completed
    ).scalar() or Decimal("0.00")

    # Total Pending (sum of unpaid amounts on sent/partially_paid invoices)
    total_pending_result = db.query(func.sum(Invoice.amount_due - Invoice.amount_paid)).filter(
        Payment.tenant_id == tenant_id,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.partially_paid])
    ).scalar() or Decimal("0.00")

    # Monthly Trend (last 6 months of revenue)
    six_months_ago = now - timedelta(days=180)
    
    monthly_revenue_query = db.query(
        extract('month', Payment.paid_at).label('month'),
        func.sum(Payment.amount).label('amount')
    ).filter(
        Payment.tenant_id == tenant_id,
        Payment.status == PaymentStatus.completed,
        Payment.paid_at >= six_months_ago
    ).group_by(
        extract('month', Payment.paid_at)
    ).order_by(
        extract('month', Payment.paid_at)
    ).all()

    # Map month numbers to names
    month_names = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
    }

    monthly_trend = [
        MonthlyRevenueItem(
            month=month_names[int(row.month)],
            amount=Decimal(str(row.amount))
        )
        for row in monthly_revenue_query
    ]

    # Calculate average monthly revenue
    avg_monthly_revenue = total_revenue_result / 6 if monthly_trend else Decimal("0.00")

    revenue_overview = RevenueOverview(
        avg_monthly_revenue=avg_monthly_revenue,
        total_revenue=total_revenue_result,
        total_pending=total_pending_result,
        monthly_trend=monthly_trend
    )

    # =====================================================
    # 2. INVOICE STATUS SUMMARY
    # =====================================================
    
    # Count invoices by status
    paid_count = db.query(func.count(Invoice.id)).filter(
        Invoice.tenant_id == tenant_id,
        Invoice.status == InvoiceStatus.paid
    ).scalar() or 0

    pending_count = db.query(func.count(Invoice.id)).filter(
        Invoice.tenant_id == tenant_id,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.partially_paid])
    ).scalar() or 0

    overdue_count = db.query(func.count(Invoice.id)).filter(
        Invoice.tenant_id == tenant_id,
        Invoice.status == InvoiceStatus.overdue
    ).scalar() or 0

    total_invoices = paid_count + pending_count + overdue_count

    # Calculate percentages
    paid_percentage = (paid_count / total_invoices * 100) if total_invoices > 0 else 0.0
    pending_percentage = (pending_count / total_invoices * 100) if total_invoices > 0 else 0.0
    overdue_percentage = (overdue_count / total_invoices * 100) if total_invoices > 0 else 0.0

    # Collection rate (paid invoices / total invoices)
    collection_rate = (paid_count / total_invoices * 100) if total_invoices > 0 else 0.0

    invoice_status = InvoiceStatusSummary(
        paid_count=paid_count,
        pending_count=pending_count,
        overdue_count=overdue_count,
        paid_percentage=round(paid_percentage, 1),
        pending_percentage=round(pending_percentage, 1),
        overdue_percentage=round(overdue_percentage, 1),
        collection_rate=round(collection_rate, 1)
    )

    # =====================================================
    # 3. CONTRACT HEALTH
    # =====================================================
    
    signed_count = db.query(func.count(Contract.id)).filter(
        Contract.tenant_id == tenant_id,
        Contract.status == ContractStatus.signed
    ).scalar() or 0

    draft_count = db.query(func.count(Contract.id)).filter(
        Contract.tenant_id == tenant_id,
        Contract.status == ContractStatus.draft
    ).scalar() or 0

    sent_count = db.query(func.count(Contract.id)).filter(
        Contract.tenant_id == tenant_id,
        Contract.status == ContractStatus.sent
    ).scalar() or 0

    total_contracts = signed_count + draft_count + sent_count

    # Calculate percentages
    signed_percentage = (signed_count / total_contracts * 100) if total_contracts > 0 else 0.0
    draft_percentage = (draft_count / total_contracts * 100) if total_contracts > 0 else 0.0
    sent_percentage = (sent_count / total_contracts * 100) if total_contracts > 0 else 0.0

    contract_health = ContractHealth(
        signed_count=signed_count,
        draft_count=draft_count,
        sent_count=sent_count,
        signed_percentage=round(signed_percentage, 1),
        draft_percentage=round(draft_percentage, 1),
        sent_percentage=round(sent_percentage, 1),
        total_active=signed_count  # Only signed contracts are "active"
    )

    # =====================================================
    # 4. RECENT ACTIVITY (Keep existing logic)
    # =====================================================
    
    activities: List[ActivityItem] = []

    # Fetch recent payments (last 3)
    recent_payments = db.query(Payment, Invoice.invoice_number, Booking.id.label('booking_id')).join(
        Invoice, Payment.invoice_id == Invoice.id, isouter=True
    ).join(
        Booking, Invoice.booking_id == Booking.id, isouter=True
    ).filter(
        Payment.tenant_id == tenant_id,
        Payment.status == PaymentStatus.completed
    ).order_by(Payment.paid_at.desc()).limit(3).all()

    for p, inv_num, booking_id in recent_payments:
        ref_text = f"({p.reference})" if p.reference else ""
        activities.append(ActivityItem(
            id=f"pay_{p.id}",
            type="payment_received",
            title="Payment Received",
            description=f"KES {p.amount:,.2f} {ref_text}",
            timestamp=p.paid_at or p.created_at,
            link=f"/dashboard/bookings/{booking_id}" if booking_id else "/dashboard/payments"
        ))

    # Fetch recent signed contracts (last 2)
    recent_contracts = db.query(Contract, Booking.id.label('booking_id')).join(
        Booking, Contract.booking_id == Booking.id
    ).filter(
        Contract.tenant_id == tenant_id,
        Contract.status == ContractStatus.signed
    ).order_by(Contract.client_signed_at.desc()).limit(2).all()

    for c, booking_id in recent_contracts:
        activities.append(ActivityItem(
            id=f"con_{c.id}",
            type="contract_signed",
            title="Contract Signed",
            description=f"Contract #{c.contract_number} signed",
            timestamp=c.client_signed_at or c.created_at,
            link=f"/dashboard/bookings/{booking_id}"
        ))

    # Sort by timestamp and take top 5
    activities.sort(key=lambda x: x.timestamp, reverse=True)
    recent_activity = activities[:5]

    # =====================================================
    # RETURN COMBINED RESPONSE
    # =====================================================
    
    return FinancialOverviewOut(
        revenue_overview=revenue_overview,
        invoice_status=invoice_status,
        contract_health=contract_health,
        recent_activity=recent_activity
    )

# app/routers/booking/extensions.py
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.bookings import Booking, BookingStatus
from app.models.invoices import Invoice, InvoiceStatus
from app.models.users import User
from app.models.vehicles import Vehicle
from app.schemas.booking import ExtendBookingPayload

router = APIRouter()

def _get_booking_or_404(booking_id: int, tenant_id: int, db: Session) -> Booking:
    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.tenant_id == tenant_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking

@router.post("/{booking_id}/extend", response_model=dict)
def extend_booking(
    booking_id: int,
    payload: ExtendBookingPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    
    if booking.status not in (BookingStatus.active, BookingStatus.completed):
        raise HTTPException(400, "Only active or completed bookings can be extended.")
        
    if payload.new_end_date <= booking.end_date:
        raise HTTPException(400, "New end date must be after the current end date.")
        
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
    if not vehicle:
        raise HTTPException(404, "Linked vehicle not found.")

    if booking.original_end_date is None:
        booking.original_end_date = booking.end_date

    extra_days = (payload.new_end_date - booking.end_date).days
    if extra_days <= 0:
        extra_days = 1
        
    additional_cost = Decimal(str(extra_days)) * (vehicle.daily_rate or Decimal("0"))

    booking.end_date = payload.new_end_date
    booking.notes = f"{booking.notes or ''}\n[Extended]: {payload.extension_reason}".strip() if payload.extension_reason else booking.notes

    invoice = db.query(Invoice).filter(Invoice.booking_id == booking.id).first()
    if invoice:
        invoice.amount_due = (invoice.amount_due or Decimal("0")) + additional_cost
        
        if invoice.status == InvoiceStatus.paid:
            invoice.status = InvoiceStatus.partially_paid
            
        invoice.notes = f"{invoice.notes or ''}\n[Extension Charge]: {extra_days} days @ {vehicle.daily_rate}/day = {additional_cost}".strip()

    db.commit()
    db.refresh(booking)

    return {
        "message": "Booking extended successfully",
        "booking_id": booking.id,
        "extra_days": extra_days,
        "additional_cost": float(additional_cost),
        "new_end_date": booking.end_date.isoformat(),
        "invoice_updated": bool(invoice)
    }

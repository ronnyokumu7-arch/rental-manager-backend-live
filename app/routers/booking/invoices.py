# app/routers/booking/invoices.py
import os
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.bookings import Booking
from app.models.users import User
from app.services.invoices import create_invoice_for_booking

router = APIRouter()

def _get_booking_or_404(booking_id: int, tenant_id: int, db: Session) -> Booking:
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.tenant_id == tenant_id,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking

@router.post("/{booking_id}/generate-invoice")
def generate_invoice(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    invoice = create_invoice_for_booking(booking, db)
    if not invoice.share_token or (invoice.share_token_expires_at and invoice.share_token_expires_at < datetime.now(timezone.utc)):
        invoice.share_token = str(uuid.uuid4())
        invoice.share_token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        db.commit()
        db.refresh(invoice)
    base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return {
        "share_url": f"{base_url}/invoice/{invoice.share_token}",
        "token": invoice.share_token,
        "expires_at": invoice.share_token_expires_at.isoformat() if invoice.share_token_expires_at else None
    }

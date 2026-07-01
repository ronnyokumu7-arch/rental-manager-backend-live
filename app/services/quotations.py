# backend/app/services/quotations.py
from datetime import datetime, timedelta, timezone
import uuid
from sqlalchemy.orm import Session
from app.models.quotations import Quotation, QuotationStatus
from app.models.bookings import Booking

def create_quotation_from_booking(booking: Booking, db: Session) -> Quotation:
    """Create a quotation linked to a booking."""
    quotation = Quotation(
        tenant_id=booking.tenant_id,
        client_id=booking.client_id,
        vehicle_id=booking.vehicle_id,
        start_date=booking.start_date,
        end_date=booking.end_date,
        pickup_location=booking.pickup_location,
        return_location=booking.return_location,
        destination=booking.destination,
        total_amount=booking.total_amount,
        currency_code=booking.currency_code,
        booking_id=booking.id,
        share_token=str(uuid.uuid4()),
        share_token_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        status=QuotationStatus.pending
    )
    db.add(quotation)
    db.commit()
    db.refresh(quotation)
    return quotation

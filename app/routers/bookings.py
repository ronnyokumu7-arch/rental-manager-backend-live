# backend/app/routers/bookings.py
import os
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.bookings import Booking, BookingStatus
from app.models.clients import Client, ClientStatus
from app.models.quotations import Quotation, QuotationStatus
from app.models.users import User
from app.models.vehicles import Vehicle, VehicleStatus
from app.schemas.booking import BookingCreate, BookingOut, BookingUpdate
from app.services.contracts import create_contract_for_booking
from app.services.invoices import create_invoice_for_booking
from app.services.email import (
    send_booking_activated,
    send_booking_cancelled,
    send_booking_completed,
    send_booking_confirmed,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])

def _get_booking_or_404(booking_id: int, tenant_id: int, db: Session) -> Booking:
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.tenant_id == tenant_id,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking

# ---------------------------------------------------------------------------
# LIST BOOKINGS
# ---------------------------------------------------------------------------
@router.get("/", response_model=list[BookingOut])
def list_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    return db.query(Booking).filter(
        Booking.tenant_id == current_user.tenant_id,
        Booking.is_archived == False,
    ).order_by(Booking.created_at.desc()).all()

@router.get("/archived", response_model=list[BookingOut])
def list_archived_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    return db.query(Booking).filter(
        Booking.tenant_id == current_user.tenant_id,
        Booking.is_archived == True,
    ).order_by(Booking.archived_at.desc()).all()

# ---------------------------------------------------------------------------
# GET SINGLE BOOKING
# ---------------------------------------------------------------------------
@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    return _get_booking_or_404(booking_id, current_user.tenant_id, db)

# ---------------------------------------------------------------------------
# CREATE BOOKING (With Custom BK-Number Generation)
# ---------------------------------------------------------------------------
@router.post("/", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    booking: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    client = db.query(Client).filter(
        Client.id == booking.client_id,
        Client.tenant_id == current_user.tenant_id,
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    if client.status == ClientStatus.suspended or client.is_archived:
        raise HTTPException(status_code=400, detail="Client cannot make bookings.")

    vehicle = db.query(Vehicle).filter(
        Vehicle.id == booking.vehicle_id,
        Vehicle.tenant_id == current_user.tenant_id,
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    if vehicle.status != VehicleStatus.available or vehicle.is_archived:
        raise HTTPException(status_code=409, detail="Vehicle is not available.")

    # ✅ GENERATE CUSTOM BOOKING NUMBER (e.g., BK-010626)
    now = datetime.now(timezone.utc)
    current_month = now.month
    current_year = now.year % 100
    
    # Find the last booking number for this specific month and year
    prefix = f"BK-%{current_month:02d}{current_year:02d}"
    last_booking = db.query(Booking.booking_number).filter(
        Booking.booking_number.like(prefix)
    ).order_by(Booking.booking_number.desc()).first()
    
    if last_booking and last_booking[0]:
        # Extract counter from "BK-010626" -> "01" -> 1
        last_counter = int(last_booking[0].split("-")[1][:2])
        new_counter = last_counter + 1
    else:
        new_counter = 1
        
    new_booking_number = f"BK-{new_counter:02d}{current_month:02d}{current_year:02d}"

    # Create the booking object
    db_booking = Booking(
        **booking.model_dump(),
        tenant_id=current_user.tenant_id,
        status=BookingStatus.pending,
        booking_number=new_booking_number, # ✅ Assign the custom ID
    )
    
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

# ---------------------------------------------------------------------------
# UPDATE BOOKING
# ---------------------------------------------------------------------------
@router.patch("/{booking_id}", response_model=BookingOut)
def update_booking(
    booking_id: int,
    booking_update: BookingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    update_data = booking_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(booking, field, value)
    db.commit()
    db.refresh(booking)
    return booking

# ---------------------------------------------------------------------------
# GENERATE QUOTATION FROM BOOKING
# ---------------------------------------------------------------------------
@router.post("/{booking_id}/generate-quotation")
def generate_quotation(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    
    if booking.status != BookingStatus.pending:
        raise HTTPException(status_code=400, detail="Can only generate quotation for pending bookings")

    # Check if quotation already exists for this booking
    quotation = db.query(Quotation).filter(Quotation.booking_id == booking.id).first()
    
    if not quotation:
        quotation = Quotation(
            tenant_id=booking.tenant_id,
            client_id=booking.client_id,
            vehicle_id=booking.vehicle_id,
            start_date=booking.start_date,
            end_date=booking.end_date,
            pickup_location=booking.pickup_location,
            return_location=booking.return_location,
            destination=booking.destination,
            daily_rate=booking.daily_rate,
            total_amount=booking.total_amount,
            currency_code=booking.currency_code,
            booking_id=booking.id,
            share_token=str(uuid.uuid4()),
            share_token_expires_at=datetime.now(timezone.utc) + timedelta(days=7)
        )
        db.add(quotation)
    else:
        # Regenerate token if it was lost or expired
        if not quotation.share_token or (quotation.share_token_expires_at and quotation.share_token_expires_at < datetime.now(timezone.utc)):
            quotation.share_token = str(uuid.uuid4())
            quotation.share_token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            quotation.status = QuotationStatus.pending

    db.commit()
    db.refresh(quotation)
    
    base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return {
        "share_url": f"{base_url}/quote/{quotation.share_token}",
        "token": quotation.share_token,
        "expires_at": quotation.share_token_expires_at
    }

# ---------------------------------------------------------------------------
# CONFIRM BOOKING
# ---------------------------------------------------------------------------
@router.post("/{booking_id}/confirm", response_model=BookingOut)
def confirm_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status != BookingStatus.pending:
        raise HTTPException(400, "Only pending bookings can be confirmed.")
    
    booking.status = BookingStatus.confirmed
    create_contract_for_booking(booking, db)
    create_invoice_for_booking(booking, db)
    db.commit()
    db.refresh(booking)
    
    client = db.query(Client).filter(Client.id == booking.client_id).first()
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
    if client and client.email:
        send_booking_confirmed(
            to=client.email,
            client_name=client.full_name,
            booking_id=booking.id,
            vehicle=f"{vehicle.make} {vehicle.model}",
            start_date=str(booking.start_date),
        )
    return booking

# ---------------------------------------------------------------------------
# ACTIVATE BOOKING
# ---------------------------------------------------------------------------
@router.post("/{booking_id}/activate", response_model=BookingOut)
def activate_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status != BookingStatus.confirmed:
        raise HTTPException(400, "Only confirmed bookings can be activated.")
    
    client = db.query(Client).filter(Client.id == booking.client_id).first()
    if client.status != ClientStatus.active:
        raise HTTPException(400, "Client must be active.")
    
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
    if vehicle.status != VehicleStatus.available:
        raise HTTPException(400, "Vehicle is not available.")
    
    booking.status = BookingStatus.active
    vehicle.status = VehicleStatus.rented
    db.commit()
    db.refresh(booking)
    
    if client.email:
        send_booking_activated(
            to=client.email,
            client_name=client.full_name,
            booking_id=booking.id,
            vehicle=f"{vehicle.make} {vehicle.model}",
            end_date=str(booking.end_date),
        )
    return booking

# ---------------------------------------------------------------------------
# COMPLETE BOOKING
# ---------------------------------------------------------------------------
@router.post("/{booking_id}/complete", response_model=BookingOut)
def complete_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status != BookingStatus.active:
        raise HTTPException(400, "Only active bookings can be completed.")
    
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
    booking.status = BookingStatus.completed
    vehicle.status = VehicleStatus.available
    db.commit()
    db.refresh(booking)
    
    client = db.query(Client).filter(Client.id == booking.client_id).first()
    if client and client.email:
        send_booking_completed(
            to=client.email,
            client_name=client.full_name,
            booking_id=booking.id,
            vehicle=f"{vehicle.make} {vehicle.model}",
        )
    return booking

# ---------------------------------------------------------------------------
# CANCEL BOOKING
# ---------------------------------------------------------------------------
@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status in (BookingStatus.completed, BookingStatus.cancelled):
        raise HTTPException(400, f"Cannot cancel a {booking.status.value} booking")
    
    if booking.status == BookingStatus.active:
        vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
        if vehicle:
            vehicle.status = VehicleStatus.available
    
    booking.status = BookingStatus.cancelled
    db.commit()
    db.refresh(booking)
    
    client = db.query(Client).filter(Client.id == booking.client_id).first()
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
    if client and client.email:
        send_booking_cancelled(
            to=client.email,
            client_name=client.full_name,
            booking_id=booking.id,
            vehicle=f"{vehicle.make} {vehicle.model}",
        )
    return booking

# ---------------------------------------------------------------------------
# NO-SHOW BOOKING
# ---------------------------------------------------------------------------
@router.post("/{booking_id}/no-show", response_model=BookingOut)
def no_show_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status != BookingStatus.confirmed:
        raise HTTPException(400, "Only confirmed bookings can be marked as no-show.")
    
    booking.status = BookingStatus.no_show
    db.commit()
    db.refresh(booking)
    return booking

# ---------------------------------------------------------------------------
# ARCHIVE BOOKING
# ---------------------------------------------------------------------------
@router.post("/{booking_id}/archive", response_model=BookingOut)
def archive_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status == BookingStatus.active:
        raise HTTPException(400, "Active bookings cannot be archived")
    if booking.is_archived:
        raise HTTPException(400, "Booking is already archived")
    
    booking.is_archived = True
    booking.archived_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(booking)
    return booking

# ---------------------------------------------------------------------------
# RESTORE BOOKING
# ---------------------------------------------------------------------------
@router.post("/{booking_id}/restore", response_model=BookingOut)
def restore_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if not booking.is_archived:
        raise HTTPException(400, "Booking is not archived")
    
    booking.is_archived = False
    booking.archived_at = None
    db.commit()
    db.refresh(booking)
    return booking

# ---------------------------------------------------------------------------
# DELETE BOOKING
# ---------------------------------------------------------------------------
@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status == BookingStatus.active:
        raise HTTPException(400, "Active bookings cannot be deleted.")
    db.delete(booking)
    db.commit()

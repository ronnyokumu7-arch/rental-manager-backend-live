# app/routers/bookings.py
import os
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.bookings import Booking, BookingStatus
from app.models.clients import Client, ClientStatus
from app.models.users import User
from app.models.vehicles import Vehicle, VehicleStatus
from app.schemas.booking import BookingCreate, BookingOut, BookingUpdate
from app.services.contracts import create_contract_for_booking
from app.services.invoices import create_invoice_for_booking
from app.services.booking_tasks import BookingTaskService # ✅ NEW
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
# ROUTES
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[BookingOut])
def list_bookings(
    vehicle_id: int = Query(None, description="Filter bookings by vehicle ID"),
    client_id: int = Query(None, description="Filter bookings by client ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    query = db.query(Booking).filter(
        Booking.tenant_id == current_user.tenant_id,
        Booking.is_archived == False,
    )
    if vehicle_id is not None:
        query = query.filter(Booking.vehicle_id == vehicle_id)
    if client_id is not None:
        query = query.filter(Booking.client_id == client_id)
    return query.order_by(Booking.created_at.desc()).all()

@router.get("/archived", response_model=list[BookingOut])
def list_archived_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    return db.query(Booking).filter(
        Booking.tenant_id == current_user.tenant_id,
        Booking.is_archived == True,
    ).order_by(Booking.archived_at.desc()).all()

@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    return _get_booking_or_404(booking_id, current_user.tenant_id, db)

# ---------------------------------------------------------------------------
# CREATE BOOKING (✅ NEW: Task Triggers Injected)
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

    # Generate Custom Booking Number (Format: YYMM-XX e.g., 2607-01)
    now = datetime.now(timezone.utc)
    yy = now.year % 100
    mm = now.month
    prefix = f"{yy:02d}{mm:02d}"
    
    last_booking = db.query(Booking.booking_number).filter(
        Booking.booking_number.like(f"{prefix}-%")
    ).order_by(Booking.booking_number.desc()).first()
    
    if last_booking and last_booking[0]:
        try:
            last_counter = int(last_booking[0].split("-")[1])
            new_counter = last_counter + 1
        except (ValueError, IndexError):
            new_counter = 1
    else:
        new_counter = 1
        
    new_booking_number = f"{prefix}-{new_counter:02d}"

    db_booking = Booking(
        **booking.model_dump(),
        tenant_id=current_user.tenant_id,
        status=BookingStatus.pending,
        booking_number=new_booking_number,
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    
    # ✅ NEW EVENT TRIGGER: Generate initial workflow tasks
    BookingTaskService.on_booking_created(db, db_booking, client.full_name, vehicle.plate_number)
    
    return db_booking

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
        "expires_at": invoice.share_token_expires_at
    }

# ---------------------------------------------------------------------------
# LIFECYCLE TRANSITIONS (✅ TASK TRIGGERS INJECTED HERE)
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
    
    # ✅ Fetch data needed for task descriptions
    client = db.query(Client).filter(Client.id == booking.client_id).first()
    
    # ✅ NEW EVENT TRIGGER
    if client:
        BookingTaskService.on_booking_confirmed(db, booking, client.full_name)
    
    if client and client.email:
        vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
        send_booking_confirmed(
            to=client.email,
            client_name=client.full_name,
            booking_id=booking.id,
            vehicle=f"{vehicle.make} {vehicle.model}" if vehicle else "N/A",
            start_date=str(booking.start_date),
        )
    return booking

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
    
    # ✅ NEW EVENT TRIGGER
    BookingTaskService.on_trip_started(db, booking, vehicle.plate_number)
    
    if client.email:
        send_booking_activated(
            to=client.email,
            client_name=client.full_name,
            booking_id=booking.id,
            vehicle=f"{vehicle.make} {vehicle.model}",
            end_date=str(booking.end_date),
        )
    return booking

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
    if vehicle:
        vehicle.status = VehicleStatus.available
    db.commit()
    db.refresh(booking)
    
    # ✅ Fetch data needed for task descriptions
    client = db.query(Client).filter(Client.id == booking.client_id).first()
    
    # ✅ NEW EVENT TRIGGER
    if client and vehicle:
        BookingTaskService.on_trip_completed(db, booking, client.full_name, vehicle.plate_number)
    
    if client and client.email:
        send_booking_completed(
            to=client.email,
            client_name=client.full_name,
            booking_id=booking.id,
            vehicle=f"{vehicle.make} {vehicle.model}" if vehicle else "N/A",
        )
    return booking

@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status in (BookingStatus.completed, BookingStatus.cancelled):
        raise HTTPException(400, f"Cannot cancel a {booking.status.value} booking")
        
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
    if booking.status == BookingStatus.active and vehicle:
        vehicle.status = VehicleStatus.available
        
    booking.status = BookingStatus.cancelled
    db.commit()
    db.refresh(booking)
    
    # ✅ NEW EVENT TRIGGER
    if vehicle:
        BookingTaskService.on_booking_cancelled(db, booking, vehicle.plate_number)
    
    client = db.query(Client).filter(Client.id == booking.client_id).first()
    if client and client.email:
        send_booking_cancelled(
            to=client.email,
            client_name=client.full_name,
            booking_id=booking.id,
            vehicle=f"{vehicle.make} {vehicle.model}" if vehicle else "N/A",
        )
    return booking

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

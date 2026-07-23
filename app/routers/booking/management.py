# app/routers/booking/management.py
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.dependencies.auth import get_current_user  # ✅ Use this instead
from app.models.bookings import Booking, BookingStatus
from app.models.clients import Client, ClientStatus
from app.models.users import User
from app.models.vehicles import Vehicle, VehicleStatus
from app.schemas.booking import BookingCreate, BookingOut, BookingUpdate
from app.services.booking_tasks import BookingTaskService

router = APIRouter()

def _get_booking_or_404(booking_id: int, tenant_id: int, db: Session) -> Booking:
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.tenant_id == tenant_id,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking

@router.get("/", response_model=list[BookingOut])
def list_bookings(
    vehicle_id: int = Query(None),
    client_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), # ✅ FIXED
):
    query = db.query(Booking).options(
        joinedload(Booking.client),
        joinedload(Booking.vehicle)
    ).filter(
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
    current_user: User = Depends(get_current_user), # ✅ FIXED
):
    return db.query(Booking).options(
        joinedload(Booking.client),
        joinedload(Booking.vehicle)
    ).filter(
        Booking.tenant_id == current_user.tenant_id,
        Booking.is_archived == True,
    ).order_by(Booking.archived_at.desc()).all()

@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), # ✅ FIXED
):
    booking = db.query(Booking).options(
        joinedload(Booking.client),
        joinedload(Booking.vehicle),
        joinedload(Booking.invoices) 
    ).filter(
        Booking.id == booking_id,
        Booking.tenant_id == current_user.tenant_id,
    ).first()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking

@router.post("/", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    booking: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), # ✅ FIXED
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
    
    BookingTaskService.on_booking_created(db, db_booking, client.full_name, vehicle.plate_number)
    return db_booking

@router.patch("/{booking_id}", response_model=BookingOut)
def update_booking(
    booking_id: int,
    booking_update: BookingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), # ✅ FIXED
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    update_data = booking_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(booking, field, value)
    db.commit()
    db.refresh(booking)
    return booking

@router.post("/{booking_id}/archive", response_model=BookingOut)
def archive_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), # ✅ FIXED
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
    current_user: User = Depends(get_current_user), # ✅ FIXED
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
    current_user: User = Depends(get_current_user), # ✅ FIXED
):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status == BookingStatus.active:
        raise HTTPException(400, "Active bookings cannot be deleted.")
    db.delete(booking)
    db.commit()

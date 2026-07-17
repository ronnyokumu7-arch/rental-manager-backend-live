# app/routers/booking/lifecycle.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.bookings import Booking, BookingStatus
from app.models.clients import Client, ClientStatus
from app.models.users import User
from app.models.vehicles import Vehicle, VehicleStatus
from app.services.contracts import create_contract_for_booking
from app.services.invoices import create_invoice_for_booking
from app.services.booking_tasks import BookingTaskService
from app.services.email import (
    send_booking_activated,
    send_booking_cancelled,
    send_booking_completed,
    send_booking_confirmed,
)

router = APIRouter()

def _get_booking_or_404(booking_id: int, tenant_id: int, db: Session) -> Booking:
    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.tenant_id == tenant_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking

@router.post("/{booking_id}/confirm", response_model=dict)
def confirm_booking(booking_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_active_subscription)):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status != BookingStatus.pending:
        raise HTTPException(400, "Only pending bookings can be confirmed.")
        
    booking.status = BookingStatus.confirmed
    create_contract_for_booking(booking, db)
    create_invoice_for_booking(booking, db)
    db.commit()
    db.refresh(booking)
    
    client = db.query(Client).filter(Client.id == booking.client_id).first()
    if client:
        BookingTaskService.on_booking_confirmed(db, booking, client.full_name)
        if client.email:
            vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
            send_booking_confirmed(to=client.email, client_name=client.full_name, booking_id=booking.id, vehicle=f"{vehicle.make} {vehicle.model}" if vehicle else "N/A", start_date=str(booking.start_date))
    return booking

@router.post("/{booking_id}/activate", response_model=dict)
def activate_booking(booking_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_active_subscription)):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status != BookingStatus.confirmed:
        raise HTTPException(400, "Only confirmed bookings can be activated.")
        
    client = db.query(Client).filter(Client.id == booking.client_id).first()
    if client and client.status != ClientStatus.active:
        raise HTTPException(400, "Client must be active.")
        
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
    if not vehicle or vehicle.status != VehicleStatus.available:
        raise HTTPException(400, "Vehicle is not available.")

    booking.status = BookingStatus.active
    vehicle.status = VehicleStatus.rented
    db.commit()
    db.refresh(booking)
    
    BookingTaskService.on_trip_started(db, booking, vehicle.plate_number)
    if client and client.email:
        send_booking_activated(to=client.email, client_name=client.full_name, booking_id=booking.id, vehicle=f"{vehicle.make} {vehicle.model}", end_date=str(booking.end_date))
    return booking

@router.post("/{booking_id}/complete", response_model=dict)
def complete_booking(booking_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_active_subscription)):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status != BookingStatus.active:
        raise HTTPException(400, "Only active bookings can be completed.")
        
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
    booking.status = BookingStatus.completed
    
    # ✅ CRITICAL CHANGE: Vehicle now requires mileage update before becoming available
    if vehicle:
        vehicle.status = VehicleStatus.awaiting_mileage
        
    db.commit()
    db.refresh(booking)
    
    client = db.query(Client).filter(Client.id == booking.client_id).first()
    if client and vehicle:
        BookingTaskService.on_trip_completed(db, booking, client.full_name, vehicle.plate_number)
        if client.email:
            send_booking_completed(to=client.email, client_name=client.full_name, booking_id=booking.id, vehicle=f"{vehicle.make} {vehicle.model}" if vehicle else "N/A")
    return booking

@router.post("/{booking_id}/cancel", response_model=dict)
def cancel_booking(booking_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_active_subscription)):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status in (BookingStatus.completed, BookingStatus.cancelled):
        raise HTTPException(400, f"Cannot cancel a {booking.status.value} booking")
        
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
    if booking.status == BookingStatus.active and vehicle:
        vehicle.status = VehicleStatus.available 
        
    booking.status = BookingStatus.cancelled
    db.commit()
    db.refresh(booking)
    
    if vehicle:
        BookingTaskService.on_booking_cancelled(db, booking, vehicle.plate_number)
    
    client = db.query(Client).filter(Client.id == booking.client_id).first()
    if client and client.email:
        send_booking_cancelled(to=client.email, client_name=client.full_name, booking_id=booking.id, vehicle=f"{vehicle.make} {vehicle.model}" if vehicle else "N/A")
    return booking

@router.post("/{booking_id}/no-show", response_model=dict)
def no_show_booking(booking_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_active_subscription)):
    booking = _get_booking_or_404(booking_id, current_user.tenant_id, db)
    if booking.status != BookingStatus.confirmed:
        raise HTTPException(400, "Only confirmed bookings can be marked as no-show.")
    booking.status = BookingStatus.no_show
    db.commit()
    db.refresh(booking)
    return booking

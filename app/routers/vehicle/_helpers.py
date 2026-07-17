# app/routers/vehicle/_helpers.py
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.users import User
from app.models.vehicles import Vehicle

def get_authorized_vehicle(vehicle_id: int, user: User, db: Session) -> Vehicle:
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.tenant_id == user.tenant_id
    ).first()
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return vehicle

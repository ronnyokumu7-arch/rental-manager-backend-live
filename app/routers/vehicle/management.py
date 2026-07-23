# app/routers/vehicle/management.py
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.users import User
from app.models.vehicles import Vehicle, VehicleStatus
from app.schemas.vehicle import VehicleCreate, VehicleOut, VehicleUpdate
from app.services.vehicle_tasks import VehicleTaskService
from ._helpers import get_authorized_vehicle

router = APIRouter()

@router.post("/", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    vehicle: VehicleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    data = vehicle.model_dump()
    data["status"] = VehicleStatus.pending_activation
    
    db_vehicle = Vehicle(**data, tenant_id=current_user.tenant_id)
    db.add(db_vehicle)
    db.commit()
    db.refresh(db_vehicle)
    
    VehicleTaskService.check_completeness(db, db_vehicle, db_vehicle.tenant_id)
    VehicleTaskService.dispatch_lifecycle_tasks(db, db_vehicle, "created")
    
    return db_vehicle

@router.get("/", response_model=list[VehicleOut])
def read_vehicles(
    status: VehicleStatus | None = None, # ✅ Added status filter
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Vehicle).filter(
        Vehicle.tenant_id == current_user.tenant_id,
        Vehicle.is_archived == False,
    )
    if status:
        query = query.filter(Vehicle.status == status)
    return query.all()

@router.get("/archived", response_model=list[VehicleOut])
def read_archived_vehicles(
    status: VehicleStatus | None = None, # ✅ Added status filter
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Vehicle).filter(
        Vehicle.tenant_id == current_user.tenant_id,
        Vehicle.is_archived == True,
    )
    if status:
        query = query.filter(Vehicle.status == status)
    return query.all()

@router.get("/{vehicle_id}", response_model=VehicleOut)
def read_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_authorized_vehicle(vehicle_id, current_user, db)

@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: int,
    updates: VehicleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = get_authorized_vehicle(vehicle_id, current_user, db)
    update_data = updates.model_dump(exclude_unset=True)
    
    if "insurance_expiry" in update_data and vehicle.status != VehicleStatus.pending_activation:
        new_expiry = update_data["insurance_expiry"]
        if vehicle.insurance_expiry and new_expiry < vehicle.insurance_expiry:
            raise HTTPException(400, "Cannot backdate insurance for active vehicles. You can only extend the expiry.")
        if new_expiry <= datetime.now(timezone.utc):
            raise HTTPException(400, "Insurance expiry cannot be set to a past date.")
            
    for field, value in update_data.items():
        setattr(vehicle, field, value)
        
    db.commit()
    db.refresh(vehicle)
    
    if "current_mileage" in update_data:
        VehicleTaskService.check_maintenance_on_booking(db, vehicle, vehicle.tenant_id)
        
    return vehicle

@router.post("/{vehicle_id}/archive", response_model=VehicleOut)
def archive_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = get_authorized_vehicle(vehicle_id, current_user, db)
    if vehicle.status == VehicleStatus.rented:
        raise HTTPException(400, "Vehicle is currently rented")
    if vehicle.is_archived:
        raise HTTPException(400, "Vehicle is already archived")
        
    vehicle.is_archived = True
    vehicle.archived_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(vehicle)
    return vehicle

@router.post("/{vehicle_id}/restore", response_model=VehicleOut)
def restore_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = get_authorized_vehicle(vehicle_id, current_user, db)
    if not vehicle.is_archived:
        raise HTTPException(400, "Vehicle is not archived")
        
    vehicle.is_archived = False
    vehicle.archived_at = None
    vehicle.status = VehicleStatus.available
    db.commit()
    db.refresh(vehicle)
    return vehicle

@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = get_authorized_vehicle(vehicle_id, current_user, db)
    if vehicle.status == VehicleStatus.rented:
        raise HTTPException(400, "Vehicle is currently rented")
        
    db.delete(vehicle)
    db.commit()

# app/routers/vehicles.py
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

router = APIRouter(prefix="/vehicles", tags=["vehicles"])

def _get_authorized_vehicle(vehicle_id: int, user: User, db: Session) -> Vehicle:
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.tenant_id == user.tenant_id
    ).first()
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return vehicle

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
    
    # ✅ NEW: Check for missing critical data (Plan A/B routing)
    VehicleTaskService.check_completeness(db, db_vehicle, db_vehicle.tenant_id)
    
    # ✅ NEW: Dispatch standard lifecycle task
    VehicleTaskService.dispatch_lifecycle_tasks(db, db_vehicle, "created")
    
    return db_vehicle

@router.post("/{vehicle_id}/activate", response_model=VehicleOut)
def activate_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = _get_authorized_vehicle(vehicle_id, current_user, db)
    
    if vehicle.status != VehicleStatus.pending_activation:
        raise HTTPException(400, "Only vehicles pending activation can be activated.")
    if not vehicle.insurance_number or not vehicle.insurance_expiry:
        raise HTTPException(400, "Insurance policy number and expiry date are required before activation.")
    if vehicle.insurance_expiry <= datetime.now(timezone.utc):
        raise HTTPException(400, "Insurance is already expired. Cannot activate vehicle.")
        
    vehicle.status = VehicleStatus.available
    db.commit()
    db.refresh(vehicle)
    
    VehicleTaskService.dispatch_lifecycle_tasks(db, vehicle, "activated")
    return vehicle

@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: int,
    updates: VehicleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = _get_authorized_vehicle(vehicle_id, current_user, db)
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
    
    # ✅ NEW EVENT TRIGGER: If mileage was manually updated, check maintenance rules
    if "current_mileage" in update_data:
        VehicleTaskService.check_maintenance_on_booking(db, vehicle, vehicle.tenant_id)
        
    return vehicle

@router.get("/", response_model=list[VehicleOut])
def read_vehicles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Vehicle).filter(
        Vehicle.tenant_id == current_user.tenant_id,
        Vehicle.is_archived == False,
    ).all()

@router.get("/archived", response_model=list[VehicleOut])
def read_archived_vehicles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Vehicle).filter(
        Vehicle.tenant_id == current_user.tenant_id,
        Vehicle.is_archived == True,
    ).all()

@router.get("/{vehicle_id}", response_model=VehicleOut)
def read_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_authorized_vehicle(vehicle_id, current_user, db)

@router.post("/{vehicle_id}/maintenance", response_model=VehicleOut)
def send_to_maintenance(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = _get_authorized_vehicle(vehicle_id, current_user, db)
    
    if vehicle.status == VehicleStatus.retired:
        raise HTTPException(400, "Retired vehicles cannot be sent to maintenance")
    if vehicle.status == VehicleStatus.rented:
        raise HTTPException(400, "Vehicle is currently rented")
    if vehicle.status == VehicleStatus.maintenance:
        raise HTTPException(400, "Vehicle is already in maintenance")
        
    vehicle.status = VehicleStatus.maintenance
    db.commit()
    db.refresh(vehicle)
    
    VehicleTaskService.dispatch_lifecycle_tasks(db, vehicle, "maintenance")
    
    # ✅ NEW EVENT TRIGGER: Check insurance status when vehicle enters maintenance
    VehicleTaskService.check_insurance_on_maintenance_status(db, vehicle, vehicle.tenant_id)
    
    return vehicle

@router.post("/{vehicle_id}/reactivate", response_model=VehicleOut)
def reactivate_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = _get_authorized_vehicle(vehicle_id, current_user, db)
    
    if vehicle.status == VehicleStatus.retired:
        raise HTTPException(400, "Retired vehicles cannot be reactivated")
    if vehicle.status == VehicleStatus.available:
        raise HTTPException(400, "Vehicle is already available")
        
    vehicle.status = VehicleStatus.available
    db.commit()
    db.refresh(vehicle)
    
    VehicleTaskService.dispatch_lifecycle_tasks(db, vehicle, "reactivate")
    return vehicle

@router.post("/{vehicle_id}/retire", response_model=VehicleOut)
def retire_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = _get_authorized_vehicle(vehicle_id, current_user, db)
    
    if vehicle.status == VehicleStatus.rented:
        raise HTTPException(400, "Vehicle is currently rented")
    if vehicle.status == VehicleStatus.retired:
        raise HTTPException(400, "Vehicle is already retired")
        
    vehicle.status = VehicleStatus.retired
    db.commit()
    db.refresh(vehicle)
    
    VehicleTaskService.dispatch_lifecycle_tasks(db, vehicle, "retire")
    return vehicle

@router.post("/{vehicle_id}/archive", response_model=VehicleOut)
def archive_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = _get_authorized_vehicle(vehicle_id, current_user, db)
    
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
    vehicle = _get_authorized_vehicle(vehicle_id, current_user, db)
    
    if not vehicle.is_archived:
        raise HTTPException(400, "Vehicle is not archived")
        
    vehicle.is_archived = False
    vehicle.archived_at = None
    db.commit()
    db.refresh(vehicle)
    return vehicle

@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = _get_authorized_vehicle(vehicle_id, current_user, db)
    
    if vehicle.status == VehicleStatus.rented:
        raise HTTPException(400, "Vehicle is currently rented")
        
    db.delete(vehicle)
    db.commit()

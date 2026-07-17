# app/routers/vehicle/lifecycle.py
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.subscription import require_active_subscription
from app.models.users import User
from app.models.vehicles import Vehicle, VehicleStatus
from app.services.vehicle_tasks import VehicleTaskService
from app.schemas.vehicle import VehicleOut
from ._helpers import get_authorized_vehicle

router = APIRouter()

# ✅ NEW SCHEMA FOR MILESTONE 3
class MileageUpdatePayload(BaseModel):
    current_mileage: int = Field(gt=0, description="New odometer reading")
    next_service_km: int | None = Field(default=None, description="Optional next service interval")

@router.post("/{vehicle_id}/activate", response_model=VehicleOut)
def activate_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = get_authorized_vehicle(vehicle_id, current_user, db)
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

@router.post("/{vehicle_id}/maintenance", response_model=VehicleOut)
def send_to_maintenance(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = get_authorized_vehicle(vehicle_id, current_user, db)
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
    VehicleTaskService.check_insurance_on_maintenance_status(db, vehicle, vehicle.tenant_id)
    return vehicle

@router.post("/{vehicle_id}/reactivate", response_model=VehicleOut)
def reactivate_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = get_authorized_vehicle(vehicle_id, current_user, db)
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
    vehicle = get_authorized_vehicle(vehicle_id, current_user, db)
    if vehicle.status == VehicleStatus.rented:
        raise HTTPException(400, "Vehicle is currently rented")
    if vehicle.status == VehicleStatus.retired:
        raise HTTPException(400, "Vehicle is already retired")
        
    vehicle.status = VehicleStatus.retired
    db.commit()
    db.refresh(vehicle)
    
    VehicleTaskService.dispatch_lifecycle_tasks(db, vehicle, "retire")
    return vehicle

# =============================================================================
# ✅ MILESTONE 3 CORE: Resolve the awaiting_mileage lock
# =============================================================================
@router.patch("/{vehicle_id}/update-mileage", response_model=VehicleOut)
def update_vehicle_mileage(
    vehicle_id: int,
    payload: MileageUpdatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = get_authorized_vehicle(vehicle_id, current_user, db)
    
    # 1. Enforce State: Only vehicles awaiting mileage can use this specific endpoint
    if vehicle.status != VehicleStatus.awaiting_mileage:
        raise HTTPException(400, "Mileage can only be updated for vehicles currently awaiting mileage.")
        
    # 2. Validate Logic: Odometer must move forward
    if payload.current_mileage <= vehicle.current_mileage:
        raise HTTPException(400, "New mileage must be strictly greater than the current mileage.")
        
    # 3. Apply Updates
    vehicle.current_mileage = payload.current_mileage
    if payload.next_service_km is not None:
        vehicle.next_service_km = payload.next_service_km
        
    # 4. Unlock the Fleet: Flip status back to available
    vehicle.status = VehicleStatus.available
    
    db.commit()
    db.refresh(vehicle)
    
    # 5. Trigger downstream checks (e.g., did this mileage push it over the service threshold?)
    VehicleTaskService.check_maintenance_on_booking(db, vehicle, vehicle.tenant_id)
    VehicleTaskService.dispatch_lifecycle_tasks(db, vehicle, "mileage_updated")
    
    return vehicle

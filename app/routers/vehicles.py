from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.users import User
from app.models.vehicles import Vehicle, VehicleStatus
from app.models.task import TaskPriority
from app.schemas.vehicle import VehicleCreate, VehicleOut, VehicleUpdate
from app.services.task_automation import TaskAutomationService

router = APIRouter(prefix="/vehicles", tags=["vehicles"])

# ---------------------------------------------------------------------------
# ✅ TASK DISPATCHER HELPER (Fleet Operations Engine)
# ---------------------------------------------------------------------------
def _dispatch_vehicle_tasks(vehicle: Vehicle, action: str, db: Session):
    """Generates tasks based on vehicle lifecycle events using Smart Routing."""
    tenant_id = vehicle.tenant_id
    plate = vehicle.plate_number
    now = datetime.now(timezone.utc)
    
    if action == "created": # Now means "Pending Activation"
        TaskAutomationService._smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Fleet Manager",
            title=f"Verify Documents & Inspect {plate}",
            description=f"New vehicle added. Verify VIN, upload registration/insurance, and conduct physical inspection.",
            category="fleet", priority=TaskPriority.high,
            due_date=now + timedelta(hours=24),
            target_type="vehicle", target_id=vehicle.id
        )
    elif action == "activated": # Transitioned to Available
        TaskAutomationService._smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Dispatcher",
            title=f"Conduct Pre-Rental Safety Check for {plate}",
            description=f"Vehicle is now live. Ensure it is cleaned, fueled, and ready for handover.",
            category="fleet", priority=TaskPriority.medium,
            due_date=now + timedelta(hours=12),
            target_type="vehicle", target_id=vehicle.id
        )
    elif action == "maintenance":
        TaskAutomationService._smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Fleet Manager",
            title=f"Track Maintenance Progress for {plate}",
            description=f"Vehicle sent to maintenance. Track service progress and update logs upon return.",
            category="fleet", priority=TaskPriority.medium,
            due_date=now + timedelta(days=3),
            target_type="vehicle", target_id=vehicle.id
        )
    elif action == "reactivate":
        TaskAutomationService._smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Fleet Manager",
            title=f"Post-Maintenance Check for {plate}",
            description=f"Vehicle reactivated. Log ending mileage and conduct post-service safety check.",
            category="fleet", priority=TaskPriority.high,
            due_date=now + timedelta(hours=12),
            target_type="vehicle", target_id=vehicle.id
        )
    elif action == "retire":
        TaskAutomationService._smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Manager",
            title=f"Process Retirement Paperwork for {plate}",
            description=f"Vehicle retired. Update asset register, remove from insurance, and process final paperwork.",
            category="fleet", priority=TaskPriority.medium,
            due_date=now + timedelta(days=7),
            target_type="vehicle", target_id=vehicle.id
        )

# ---------------------------------------------------------------------------
# Business Logic Helpers
# ---------------------------------------------------------------------------
def _get_authorized_vehicle(vehicle_id: int, user: User, db: Session) -> Vehicle:
    """Retrieve a vehicle and enforce tenant ownership."""
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id,
        Vehicle.tenant_id == user.tenant_id
    ).first()
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Vehicle not found"
        )
    return vehicle

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    vehicle: VehicleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    # ✅ FORCE STATUS: All new cars start in pending_activation
    data = vehicle.model_dump()
    data["status"] = VehicleStatus.pending_activation 
    
    db_vehicle = Vehicle(**data, tenant_id=current_user.tenant_id)
    db.add(db_vehicle)
    db.commit()
    db.refresh(db_vehicle)
    
    # ✅ TRIGGER: Vehicle Created (Pending Activation)
    _dispatch_vehicle_tasks(db_vehicle, "created", db)
    db.commit() # ✅ CRITICAL: Commit the tasks
    
    return db_vehicle

# ✅ NEW: ACTIVATION ENDPOINT (The Compliance Gate)
@router.post("/{vehicle_id}/activate", response_model=VehicleOut)
def activate_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """Transitions a vehicle from pending_activation to available. Enforces compliance."""
    vehicle = _get_authorized_vehicle(vehicle_id, current_user, db)
    
    if vehicle.status != VehicleStatus.pending_activation:
        raise HTTPException(400, "Only vehicles pending activation can be activated.")
    
    # ✅ COMPLIANCE CHECK: Must have insurance details
    if not vehicle.insurance_number or not vehicle.insurance_expiry:
        raise HTTPException(400, "Insurance policy number and expiry date are required before activation.")
        
    # ✅ BACKDATING PREVENTION: Insurance must be in the future
    if vehicle.insurance_expiry <= datetime.now(timezone.utc):
        raise HTTPException(400, "Insurance is already expired. Cannot activate vehicle.")
        
    vehicle.status = VehicleStatus.available
    db.commit()
    db.refresh(vehicle)
    
    # ✅ TRIGGER: Vehicle Activated
    _dispatch_vehicle_tasks(vehicle, "activated", db)
    db.commit() # ✅ CRITICAL: Commit the tasks
    
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
    
    # ✅ BACKDATING PREVENTION: Protect active vehicles from insurance rollback
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
        raise HTTPException(status_code=400, detail="Retired vehicles cannot be sent to maintenance")
    if vehicle.status == VehicleStatus.rented:
        raise HTTPException(status_code=400, detail="Vehicle is currently rented. Complete or cancel the active booking first")
    if vehicle.status == VehicleStatus.maintenance:
        raise HTTPException(status_code=400, detail="Vehicle is already in maintenance")
        
    vehicle.status = VehicleStatus.maintenance
    db.commit()
    db.refresh(vehicle)
    
    # ✅ TRIGGER
    _dispatch_vehicle_tasks(vehicle, "maintenance", db)
    db.commit()
    return vehicle

@router.post("/{vehicle_id}/reactivate", response_model=VehicleOut)
def reactivate_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = _get_authorized_vehicle(vehicle_id, current_user, db)
    if vehicle.status == VehicleStatus.retired:
        raise HTTPException(status_code=400, detail="Retired vehicles cannot be reactivated")
    if vehicle.status == VehicleStatus.available:
        raise HTTPException(status_code=400, detail="Vehicle is already available")
        
    vehicle.status = VehicleStatus.available
    db.commit()
    db.refresh(vehicle)
    
    # ✅ TRIGGER
    _dispatch_vehicle_tasks(vehicle, "reactivate", db)
    db.commit()
    return vehicle

@router.post("/{vehicle_id}/retire", response_model=VehicleOut)
def retire_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = _get_authorized_vehicle(vehicle_id, current_user, db)
    if vehicle.status == VehicleStatus.rented:
        raise HTTPException(status_code=400, detail="Vehicle is currently rented. Complete or cancel the active booking first")
    if vehicle.status == VehicleStatus.retired:
        raise HTTPException(status_code=400, detail="Vehicle is already retired")
        
    vehicle.status = VehicleStatus.retired
    db.commit()
    db.refresh(vehicle)
    
    # ✅ TRIGGER
    _dispatch_vehicle_tasks(vehicle, "retire", db)
    db.commit()
    return vehicle

@router.post("/{vehicle_id}/archive", response_model=VehicleOut)
def archive_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    vehicle = _get_authorized_vehicle(vehicle_id, current_user, db)
    if vehicle.status == VehicleStatus.rented:
        raise HTTPException(status_code=400, detail="Vehicle is currently rented and cannot be archived")
    if vehicle.is_archived:
        raise HTTPException(status_code=400, detail="Vehicle is already archived")
        
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
        raise HTTPException(status_code=400, detail="Vehicle is not archived")
        
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
        raise HTTPException(status_code=400, detail="Vehicle is currently rented and cannot be deleted")
    db.delete(vehicle)
    db.commit()

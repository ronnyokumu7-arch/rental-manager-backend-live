from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.vehicles import Vehicle, VehicleStatus
from app.models.task import TaskPriority
from app.services.task_core import TaskCoreService

class VehicleTaskService:
    """Handles all task generation logic specific to the Vehicle lifecycle."""

    @staticmethod
    def check_completeness(db: Session, vehicle: Vehicle, tenant_id: int):
        """Triggered when a vehicle is created. Checks for missing critical data."""
        missing_fields = []
        if not vehicle.insurance_number: missing_fields.append("Insurance Policy Number")
        if not vehicle.insurance_expiry: missing_fields.append("Insurance Expiry Date")
        if not vehicle.registration_doc: missing_fields.append("Registration Document")
        
        if missing_fields:
            missing_list = ", ".join(missing_fields)
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="Fleet Manager",
                title=f"Complete Profile for {vehicle.plate_number}",
                description=f"Vehicle is missing critical compliance data: {missing_list}. Please update the vehicle profile to enable activation.",
                category="compliance", priority=TaskPriority.high,
                due_date=datetime.now() + timedelta(hours=24),
                target_type="vehicle", target_id=vehicle.id
            )

    @staticmethod
    def check_maintenance_on_booking(db: Session, vehicle: Vehicle, tenant_id: int):
        """Triggered when a car is booked or mileage is manually updated."""
        if not vehicle.next_service_km:
            return
            
        remaining_km = vehicle.next_service_km - vehicle.current_mileage
        
        if remaining_km <= 0:
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="Fleet Manager",
                title=f"URGENT: Service Overdue for {vehicle.plate_number}",
                description=f"Vehicle is overdue for service by {abs(remaining_km):,}km. Schedule maintenance immediately.",
                category="fleet", priority=TaskPriority.high,
                due_date=datetime.now() + timedelta(days=1),
                target_type="vehicle", target_id=vehicle.id
            )
        elif remaining_km <= (vehicle.next_service_km * 0.05):
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="Fleet Manager",
                title=f"Service Due Soon for {vehicle.plate_number}",
                description=f"Vehicle is within 5% of its next service interval. Only {remaining_km:,}km remaining.",
                category="fleet", priority=TaskPriority.medium,
                due_date=datetime.now() + timedelta(days=7),
                target_type="vehicle", target_id=vehicle.id
            )

    @staticmethod
    def check_insurance_on_booking(db: Session, vehicle: Vehicle, tenant_id: int):
        """Triggered when a car is booked. Checks insurance expiry."""
        if not vehicle.insurance_expiry:
            return
            
        today = datetime.now()
        if hasattr(vehicle.insurance_expiry, 'date'):
            days_left = (vehicle.insurance_expiry.date() - today.date()).days
        else:
            days_left = (vehicle.insurance_expiry - today).days
            
        if days_left < 2:
            status_text = "OVERDUE" if days_left < 0 else f"expires in {days_left} days"
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="Fleet Manager",
                title=f"CRITICAL: Insurance {status_text} for {vehicle.plate_number}",
                description=f"Vehicle insurance {status_text}. Do not dispatch until renewed.",
                category="compliance", priority=TaskPriority.urgent,
                due_date=datetime.now(),
                target_type="vehicle", target_id=vehicle.id
            )
        elif days_left < 7:
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="Fleet Manager",
                title=f"Insurance Expiring Soon for {vehicle.plate_number}",
                description=f"Vehicle insurance expires in {days_left} days. Initiate renewal process.",
                category="compliance", priority=TaskPriority.high,
                due_date=datetime.now() + timedelta(days=2),
                target_type="vehicle", target_id=vehicle.id
            )

    @staticmethod
    def create_mileage_update_reminder(db: Session, vehicle: Vehicle, tenant_id: int):
        """Triggered when a trip ends."""
        TaskCoreService.smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Fleet Manager",
            title=f"Update Mileage for {vehicle.plate_number}",
            description=f"Trip has ended. Please update the final odometer reading to ensure accurate maintenance tracking.",
            category="fleet", priority=TaskPriority.medium,
            due_date=datetime.now() + timedelta(hours=24),
            target_type="vehicle", target_id=vehicle.id
        )

    @staticmethod
    def check_insurance_on_maintenance_status(db: Session, vehicle: Vehicle, tenant_id: int):
        """Triggered when vehicle status changes to maintenance."""
        if not vehicle.insurance_expiry:
            return
            
        today = datetime.now()
        if hasattr(vehicle.insurance_expiry, 'date'):
            days_left = (vehicle.insurance_expiry.date() - today.date()).days
        else:
            days_left = (vehicle.insurance_expiry - today).days
            
        if days_left <= 30:
            status_text = "OVERDUE" if days_left < 0 else f"expires in {days_left} days"
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="Fleet Manager",
                title=f"Renew Insurance for {vehicle.plate_number} (In Maintenance)",
                description=f"Vehicle is in maintenance and its insurance {status_text}. Perfect time to handle renewal paperwork.",
                category="compliance", priority=TaskPriority.high if days_left < 7 else TaskPriority.medium,
                due_date=datetime.now() + timedelta(days=3),
                target_type="vehicle", target_id=vehicle.id
            )

    @staticmethod
    def dispatch_lifecycle_tasks(db: Session, vehicle: Vehicle, action: str):
        """
        Replaces the old _dispatch_vehicle_tasks function in the router.
        Generates standard tasks based on vehicle status changes.
        """
        tenant_id = vehicle.tenant_id
        plate = vehicle.plate_number
        now = datetime.now()
        
        if action == "created":
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="Fleet Manager",
                title=f"Verify Documents & Inspect {plate}",
                description=f"New vehicle added. Verify VIN, upload registration/insurance, and conduct physical inspection.",
                category="fleet", priority=TaskPriority.high,
                due_date=now + timedelta(hours=24),
                target_type="vehicle", target_id=vehicle.id
            )
        elif action == "activated":
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="Dispatcher",
                title=f"Conduct Pre-Rental Safety Check for {plate}",
                description=f"Vehicle is now live. Ensure it is cleaned, fueled, and ready for handover.",
                category="fleet", priority=TaskPriority.medium,
                due_date=now + timedelta(hours=12),
                target_type="vehicle", target_id=vehicle.id
            )
        elif action == "maintenance":
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="Fleet Manager",
                title=f"Track Maintenance Progress for {plate}",
                description=f"Vehicle sent to maintenance. Track service progress and update logs upon return.",
                category="fleet", priority=TaskPriority.medium,
                due_date=now + timedelta(days=3),
                target_type="vehicle", target_id=vehicle.id
            )
        elif action == "reactivate":
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="Fleet Manager",
                title=f"Post-Maintenance Check for {plate}",
                description=f"Vehicle reactivated. Log ending mileage and conduct post-service safety check.",
                category="fleet", priority=TaskPriority.high,
                due_date=now + timedelta(hours=12),
                target_type="vehicle", target_id=vehicle.id
            )
        elif action == "retire":
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="Manager",
                title=f"Process Retirement Paperwork for {plate}",
                description=f"Vehicle retired. Update asset register, remove from insurance, and process final paperwork.",
                category="fleet", priority=TaskPriority.medium,
                due_date=now + timedelta(days=7),
                target_type="vehicle", target_id=vehicle.id
            )

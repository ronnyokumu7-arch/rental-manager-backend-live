from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.bookings import Booking, BookingStatus
from app.models.task import TaskPriority
from app.services.task_core import TaskCoreService

class BookingTaskService:
    """Handles all task generation logic specific to the Booking lifecycle."""

    @staticmethod
    def on_booking_created(db: Session, booking: Booking, client_name: str, vehicle_plate: str):
        """Triggered when a new booking is created. Sets up the initial workflow."""
        tenant_id = booking.tenant_id
        booking_id = booking.id
        now = datetime.now()

        # 1. Sales/Admin: Generate Quotation & Invoice
        TaskCoreService.smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Sales Agent",
            title=f"Generate Quotation for Booking #{booking.id}",
            description=f"New booking created for {client_name}. Generate and send the initial quotation/invoice.",
            category="finance", priority=TaskPriority.high,
            due_date=now + timedelta(hours=4),
            target_type="booking", target_id=booking_id
        )

        # 2. Contracts: Draft the Rental Agreement
        TaskCoreService.smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Contracts Officer",
            title=f"Draft Contract for Booking #{booking.id}",
            description=f"Prepare the rental agreement for {client_name} for vehicle {vehicle_plate}.",
            category="compliance", priority=TaskPriority.high,
            due_date=now + timedelta(hours=6),
            target_type="booking", target_id=booking_id
        )

        # 3. Dispatcher: Prepare the Vehicle
        TaskCoreService.smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Dispatcher",
            title=f"Prepare Vehicle {vehicle_plate} for Dispatch",
            description=f"Booking #{booking.id} starts on {booking.start_date}. Ensure vehicle {vehicle_plate} is cleaned, fueled, and ready for {client_name}.",
            category="fleet", priority=TaskPriority.medium,
            due_date=booking.start_date - timedelta(hours=2),
            target_type="booking", target_id=booking_id
        )

    @staticmethod
    def on_booking_confirmed(db: Session, booking: Booking, client_name: str):
        """Triggered when the admin confirms a pending booking."""
        tenant_id = booking.tenant_id
        booking_id = booking.id
        
        TaskCoreService.smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Contracts Officer",
            title=f"Send Contract to {client_name} (Booking #{booking.id})",
            description=f"Booking confirmed. Send the drafted contract to the client for signature.",
            category="compliance", priority=TaskPriority.high,
            due_date=datetime.now() + timedelta(hours=2),
            target_type="booking", target_id=booking_id
        )

    @staticmethod
    def on_trip_started(db: Session, booking: Booking, vehicle_plate: str):
        """Triggered when the booking status changes to 'active' (trip begins)."""
        tenant_id = booking.tenant_id
        booking_id = booking.id

        TaskCoreService.smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Dispatcher",
            title=f"Monitor Return of {vehicle_plate} (Booking #{booking.id})",
            description=f"Trip has started. Vehicle {vehicle_plate} is due back on {booking.end_date}. Monitor for any delays.",
            category="fleet", priority=TaskPriority.low,
            due_date=booking.end_date,
            target_type="booking", target_id=booking_id
        )

    @staticmethod
    def on_trip_completed(db: Session, booking: Booking, client_name: str, vehicle_plate: str):
        """Triggered when the booking status changes to 'completed' (trip ends)."""
        tenant_id = booking.tenant_id
        booking_id = booking.id
        now = datetime.now()

        # 1. Fleet: Post-trip inspection
        TaskCoreService.smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Fleet Manager",
            title=f"Post-Trip Inspection for {vehicle_plate}",
            description=f"Booking #{booking.id} for {client_name} has ended. Conduct physical inspection for damages and update final mileage.",
            category="fleet", priority=TaskPriority.high,
            due_date=now + timedelta(hours=4),
            target_type="booking", target_id=booking_id
        )

        # 2. Finance: Finalize billing
        TaskCoreService.smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Accountant",
            title=f"Finalize Invoice for Booking #{booking.id}",
            description=f"Trip completed for {client_name}. Calculate final charges (extra mileage, fuel, damages) and close the invoice.",
            category="finance", priority=TaskPriority.high,
            due_date=now + timedelta(hours=6),
            target_type="booking", target_id=booking_id
        )

    @staticmethod
    def on_booking_cancelled(db: Session, booking: Booking, vehicle_plate: str):
        """Triggered when a booking is cancelled."""
        tenant_id = booking.tenant_id
        booking_id = booking.id

        TaskCoreService.smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Accountant",
            title=f"Process Refund/Release for Booking #{booking.id}",
            description=f"Booking cancelled. Process any necessary refunds and ensure vehicle {vehicle_plate} is released back to the available fleet.",
            category="finance", priority=TaskPriority.medium,
            due_date=datetime.now() + timedelta(hours=2),
            target_type="booking", target_id=booking_id
        )

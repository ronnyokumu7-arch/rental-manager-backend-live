# app/services/task_automation.py
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.users import User
from app.models.invoices import Invoice
from app.models.vehicles import Vehicle, VehicleStatus

class TaskAutomationService:
    """Generates system tasks based on business rules with Smart Routing"""

    @staticmethod
    def generate_daily_tasks(db: Session):
        """Run daily to generate tasks"""
        today = datetime.now()

        # ---------------------------------------------------------
        # 1. Expiring Driver's Licenses (Compliance / HR Tasks)
        # ---------------------------------------------------------
        users_with_expiring_dl = db.query(User).filter(
            User.dl_expiry != None,
            User.dl_expiry.between(today, today + timedelta(days=30)),
            User.is_active == True,
            User.tenant_id != None
        ).all()

        for user in users_with_expiring_dl:
            days_left = (user.dl_expiry - today).days
            TaskAutomationService._smart_create_task(
                db=db, 
                tenant_id=user.tenant_id,
                target_role="HR", 
                title=f"Renew Driver's License ({user.full_name})",
                description=f"Driver's license for {user.full_name} expires in {days_left} days ({user.dl_expiry.strftime('%Y-%m-%d')}). Please initiate the renewal process.",
                category="compliance", 
                priority=TaskPriority.high if days_left < 7 else TaskPriority.medium,
                due_date=user.dl_expiry - timedelta(days=7),
                target_type="user", 
                target_id=user.id
            )

        # ---------------------------------------------------------
        # 2. Overdue Invoices (Finance Tasks)
        # ---------------------------------------------------------
        # Note: Adjust the status strings below if your InvoiceStatus enum uses different values (e.g., 'draft', 'sent')
        overdue_invoices = db.query(Invoice).filter(
            Invoice.status.in_(["unpaid", "overdue", "pending"]), 
            Invoice.due_date < today
        ).all()

        for invoice in overdue_invoices:
            if hasattr(invoice.due_date, 'date'):
                days_overdue = (today.date() - invoice.due_date.date()).days
            else:
                days_overdue = (today - invoice.due_date).days
            
            amount = getattr(invoice, 'total_amount', getattr(invoice, 'amount', 'N/A'))
            inv_number = getattr(invoice, 'invoice_number', getattr(invoice, 'id', 'Unknown'))
            
            TaskAutomationService._smart_create_task(
                db=db, 
                tenant_id=invoice.tenant_id,
                target_role="Accountant", 
                title=f"Follow up on Overdue Invoice #{inv_number}",
                description=f"Invoice #{inv_number} is {days_overdue} days overdue. Amount due: {amount}. Please contact the client for payment.",
                category="finance", 
                priority=TaskPriority.high if days_overdue > 14 else TaskPriority.medium,
                due_date=today + timedelta(days=1),
                target_type="invoice", 
                target_id=invoice.id
            )

        # ---------------------------------------------------------
        # 3. Vehicle Maintenance & Insurance (Fleet Tasks)
        # ---------------------------------------------------------
        vehicles = db.query(Vehicle).filter(
            Vehicle.status != VehicleStatus.retired,
            Vehicle.tenant_id != None
        ).all()

        for vehicle in vehicles:
            plate = vehicle.plate_number
            
            # A. Mileage-Based Service Due
            if vehicle.next_service_km and vehicle.current_mileage >= vehicle.next_service_km:
                km_overdue = vehicle.current_mileage - vehicle.next_service_km
                TaskAutomationService._smart_create_task(
                    db=db, 
                    tenant_id=vehicle.tenant_id,
                    target_role="Fleet Manager",
                    title=f"URGENT: Service Overdue for {plate}",
                    description=f"Vehicle {plate} has {vehicle.current_mileage:,}km. Service was due at {vehicle.next_service_km:,}km ({km_overdue:,}km overdue). Schedule maintenance immediately.",
                    category="fleet", 
                    priority=TaskPriority.high,
                    due_date=today + timedelta(days=1),
                    target_type="vehicle", 
                    target_id=vehicle.id
                )
            elif vehicle.next_service_km:
                # Warning: Service due soon (within 1000km)
                km_until_service = vehicle.next_service_km - vehicle.current_mileage
                if 0 < km_until_service <= 1000:
                    TaskAutomationService._smart_create_task(
                        db=db, 
                        tenant_id=vehicle.tenant_id,
                        target_role="Fleet Manager",
                        title=f"Service Due Soon for {plate}",
                        description=f"Vehicle {plate} has {vehicle.current_mileage:,}km. Next service due at {vehicle.next_service_km:,}km ({km_until_service:,}km remaining). Plan for upcoming maintenance.",
                        category="fleet", 
                        priority=TaskPriority.medium,
                        due_date=today + timedelta(days=7),
                        target_type="vehicle", 
                        target_id=vehicle.id
                    )

            # B. Insurance Expiring
            if vehicle.insurance_expiry:
                if hasattr(vehicle.insurance_expiry, 'date'):
                    days_left = (vehicle.insurance_expiry.date() - today.date()).days
                else:
                    days_left = (vehicle.insurance_expiry - today).days
                
                if 0 <= days_left <= 30:
                    TaskAutomationService._smart_create_task(
                        db=db, 
                        tenant_id=vehicle.tenant_id,
                        target_role="Fleet Manager",
                        title=f"Renew Insurance for {plate}",
                        description=f"Vehicle {plate} insurance expires in {days_left} days ({vehicle.insurance_expiry.strftime('%Y-%m-%d')}). Contact the insurer to renew the policy.",
                        category="compliance", 
                        priority=TaskPriority.high if days_left < 7 else TaskPriority.medium,
                        due_date=vehicle.insurance_expiry - timedelta(days=7),
                        target_type="vehicle", 
                        target_id=vehicle.id
                    )

    # -------------------------------------------------------------------
    # SMART ROUTER (Bulletproof Plan A / Plan B Logic)
    # -------------------------------------------------------------------
    @staticmethod
    def _smart_create_task(
        db: Session, 
        tenant_id: int,
        target_role: str,
        title: str, 
        description: str, 
        category: str, 
        priority: TaskPriority, 
        due_date: datetime,
        target_type: str, 
        target_id: int
    ):
        """
        SMART ROUTER: 
        1. Checks for duplicates (any active task for this target).
        2. Plan A: Matches job_title -> Assigns to user (Status: pending).
        3. Plan B: No match -> Drops to pool (Status: unassigned).
        """
        # 1. Duplicate Check (Prevents spamming the DB)
        # We check for ANY non-completed task for this target, regardless of status.
        existing = db.query(Task).filter(
            Task.tenant_id == tenant_id,
            Task.target_type == target_type,
            Task.target_id == target_id,
            Task.status != TaskStatus.completed
        ).first()
        
        if existing:
            return # Task already exists, do nothing.

        # 2. Plan A: Try to find a user with the matching job title
        assignee = db.query(User).filter(
            User.job_title == target_role,
            User.tenant_id == tenant_id,
            User.is_active == True
        ).first()

        if assignee:
            # Plan A: Direct Assignment
            final_user_id = assignee.id
            final_status = TaskStatus.pending
            final_requires_role = None
        else:
            # Plan B: Fallback to Unassigned Pool
            final_user_id = None
            final_status = TaskStatus.unassigned
            final_requires_role = target_role

        # 3. Create the Task
        task = Task(
            tenant_id=tenant_id,
            user_id=final_user_id,
            requires_role=final_requires_role,
            title=title, 
            description=description,
            category=category, 
            priority=priority, 
            due_date=due_date,
            status=final_status,
            is_system_generated=True, 
            target_type=target_type, 
            target_id=target_id
        )
        
        db.add(task)
        db.commit()

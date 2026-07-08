from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.users import User
from app.models.invoices import Invoice
from app.models.vehicles import Vehicle

class TaskAutomationService:
    """Generates system tasks based on business rules with Smart Routing"""
    
    @staticmethod
    def generate_daily_tasks(db: Session):
        """Run daily at 8:00 AM to generate tasks"""
        today = datetime.now()
        
        # 1. Expiring Driver's Licenses
        users_with_expiring_dl = db.query(User).filter(
            User.dl_expiry != None,
            User.dl_expiry.between(today, today + timedelta(days=30)),
            User.is_active == True,
            User.tenant_id != None
        ).all()
        
        for user in users_with_expiring_dl:
            days_left = (user.dl_expiry - today).days
            TaskAutomationService._smart_create_task(
                db=db, tenant_id=user.tenant_id, target_role="HR",
                title=f"Renew Driver's License ({user.full_name})",
                description=f"Driver's license expires in {days_left} days.",
                category="compliance", 
                priority=TaskPriority.high if days_left < 7 else TaskPriority.medium,
                due_date=user.dl_expiry - timedelta(days=7),
                target_type="user", target_id=user.id
            )
        
        # 2. Overdue Invoices
        overdue_invoices = db.query(Invoice).filter(
            Invoice.status.in_(["unpaid", "overdue", "pending"]), 
            Invoice.due_date < today
        ).all()
        
        for invoice in overdue_invoices:
            days_overdue = (today.date() - invoice.due_date.date()) if hasattr(invoice.due_date, 'date') else (today - invoice.due_date).days
            amount = getattr(invoice, 'total_amount', getattr(invoice, 'amount', 'N/A'))
            TaskAutomationService._smart_create_task(
                db=db, tenant_id=invoice.tenant_id, target_role="Accountant",
                title=f"Follow up on Overdue Invoice #{invoice.id}",
                description=f"Invoice is {days_overdue} days overdue. Amount: {amount}",
                category="finance", 
                priority=TaskPriority.high if days_overdue > 14 else TaskPriority.medium,
                due_date=today + timedelta(days=1),
                target_type="invoice", target_id=invoice.id
            )
        
        # 3. Vehicle Maintenance & Insurance
        vehicles = db.query(Vehicle).filter(
            Vehicle.status != "retired",
            Vehicle.tenant_id != None
        ).all()
        
        for vehicle in vehicles:
            plate = vehicle.plate_number
            # Service Due
            if vehicle.next_service_km and vehicle.current_mileage >= vehicle.next_service_km:
                TaskAutomationService._smart_create_task(
                    db=db, tenant_id=vehicle.tenant_id, target_role="Fleet Manager",
                    title=f"Schedule Service for {plate}",
                    description=f"Vehicle has {vehicle.current_mileage}km. Next service due at {vehicle.next_service_km}km.",
                    category="fleet", priority=TaskPriority.high,
                    due_date=today + timedelta(days=1),
                    target_type="vehicle", target_id=vehicle.id
                )
            # Insurance Expiring
            if vehicle.insurance_expiry:
                days_left = (vehicle.insurance_expiry.date() - today.date()).days if hasattr(vehicle.insurance_expiry, 'date') else (vehicle.insurance_expiry - today).days
                if 0 <= days_left <= 30:
                    TaskAutomationService._smart_create_task(
                        db=db, tenant_id=vehicle.tenant_id, target_role="Fleet Manager",
                        title=f"Renew Insurance for {plate}",
                        description=f"Vehicle insurance expires in {days_left} days.",
                        category="compliance", 
                        priority=TaskPriority.high if days_left < 7 else TaskPriority.medium,
                        due_date=vehicle.insurance_expiry - timedelta(days=7),
                        target_type="vehicle", target_id=vehicle.id
                    )
        
        db.commit()
    
    @staticmethod
    def _smart_create_task(
        db: Session, tenant_id: int, target_role: str,
        title: str, description: str, category: str, 
        priority: TaskPriority, due_date: datetime,
        target_type: str, target_id: int
    ):
        """
        SMART ROUTER: 
        1. Looks for an active user with the target_role in this tenant.
        2. If found, assigns directly (Status: upcoming).
        3. If NOT found, drops into Unassigned Pool (Status: unassigned).
        """
        # Check for existing duplicate tasks
        existing = db.query(Task).filter(
            Task.tenant_id == tenant_id,
            Task.target_type == target_type,
            Task.target_id == target_id,
            Task.status != TaskStatus.completed,
            Task.status != TaskStatus.unassigned
        ).first()
        if existing:
            return
        
        # Smart Routing Logic
        assignee = db.query(User).filter(
            User.job_title == target_role,
            User.tenant_id == tenant_id,
            User.is_active == True
        ).first()
        
        if assignee:
            final_user_id = assignee.id
            final_status = TaskStatus.upcoming
            final_requires_role = None
        else:
            final_user_id = None
            final_status = TaskStatus.unassigned
            final_requires_role = target_role
        
        # Create the Task
        task = Task(
            tenant_id=tenant_id,
            user_id=final_user_id,
            requires_role=final_requires_role,
            title=title, description=description,
            category=category, priority=priority, 
            due_date=due_date, status=final_status,
            is_system_generated=True, 
            target_type=target_type, target_id=target_id
        )
        db.add(task)
        db.commit()  # ✅ CRITICAL FIX: Commit the task!

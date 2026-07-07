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
            # Smart Router: Try to find HR/Manager, fallback to Unassigned Pool
            TaskAutomationService._smart_create_task(
                db=db, 
                tenant_id=user.tenant_id,
                target_role="HR", # The system will look for this role
                title=f"Renew Driver's License ({user.full_name})",
                description=f"Driver's license expires in {days_left} days ({user.dl_expiry.strftime('%Y-%m-%d')}).",
                category="compliance", 
                priority=TaskPriority.high if days_left < 7 else TaskPriority.medium,
                due_date=user.dl_expiry - timedelta(days=7),
                target_type="user", 
                target_id=user.id
            )
        
        # ---------------------------------------------------------
        # 2. Overdue Invoices (Finance Tasks)
        # ---------------------------------------------------------
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
            # Smart Router: Try to find Accountant/Credit Control
            TaskAutomationService._smart_create_task(
                db=db, 
                tenant_id=invoice.tenant_id,
                target_role="Accountant", 
                title=f"Follow up on Overdue Invoice #{inv_number}",
                description=f"Invoice is {days_overdue} days overdue. Amount: {amount}",
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
            Vehicle.status != "retired",
            Vehicle.tenant_id != None
        ).all()
        for vehicle in vehicles:
            next_service = getattr(vehicle, 'next_service_date', None)
            insurance_expiry = getattr(vehicle, 'insurance_expiry', None)
            plate = getattr(vehicle, 'plate_number', getattr(vehicle, 'license_plate', 'Vehicle'))
            # A. Service Due
            if next_service and hasattr(next_service, 'date'):
                if next_service.date() >= today.date() and next_service.date() <= (today + timedelta(days=14)).date():
                    TaskAutomationService._smart_create_task(
                        db=db, 
                        tenant_id=vehicle.tenant_id,
                        target_role="Fleet Manager",
                        title=f"Schedule Service for {plate}",
                        description=f"Vehicle is due for routine maintenance on {next_service.strftime('%Y-%m-%d')}.",
                        category="fleet", 
                        priority=TaskPriority.medium,
                        due_date=next_service,
                        target_type="vehicle", 
                        target_id=vehicle.id
                    )
            # B. Insurance Expiring
            if insurance_expiry and hasattr(insurance_expiry, 'date'):
                if insurance_expiry.date() >= today.date() and insurance_expiry.date() <= (today + timedelta(days=30)).date():
                    days_left = (insurance_expiry.date() - today.date()).days
                    TaskAutomationService._smart_create_task(
                        db=db, 
                        tenant_id=vehicle.tenant_id,
                        target_role="Fleet Manager",
                        title=f"Renew Insurance for {plate}",
                        description=f"Vehicle insurance expires in {days_left} days.",
                        category="compliance", 
                        priority=TaskPriority.high if days_left < 7 else TaskPriority.medium,
                        due_date=insurance_expiry - timedelta(days=7),
                        target_type="vehicle", 
                        target_id=vehicle.id
                    )
        db.commit()
    
    @staticmethod
    def _smart_create_task(
        db: Session, 
        tenant_id: int,
        target_role: str, # ✅ The role we are trying to assign this to
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
        1. Looks for an active user with the target_role in this tenant.
        2. If found, assigns directly (Status: upcoming).
        3. If NOT found, drops into Unassigned Pool (Status: unassigned).
        """
        # 1. Check for existing duplicate tasks
        existing = db.query(Task).filter(
            Task.tenant_id == tenant_id,
            Task.target_type == target_type,
            Task.target_id == target_id,
            Task.status != TaskStatus.completed,
            Task.status != TaskStatus.unassigned # Allow unassigned tasks to be re-evaluated
        ).first()
        if existing:
            return
        # 2. Smart Routing Logic
        assignee = db.query(User).filter(
            User.job_title == target_role,
            User.tenant_id == tenant_id,
            User.is_active == True
        ).first()
        if assignee:
            # Primary Routing: Assign to the actual user
            final_user_id = assignee.id
            final_status = TaskStatus.upcoming
            final_requires_role = None
        else:
            # Fallback: Send to the Unassigned Pool
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

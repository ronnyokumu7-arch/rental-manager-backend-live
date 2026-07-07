from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.users import User
from app.models.invoices import Invoice
from app.models.vehicles import Vehicle

class TaskAutomationService:
    """Generates system tasks based on business rules"""
    
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
            User.tenant_id != None # Only tenant users
        ).all()
        
        for user in users_with_expiring_dl:
            days_left = (user.dl_expiry - today).days
            
            # Assign to the user themselves (self-reminder) AND their HR/Manager
            assignees = [user]
            hr_managers = db.query(User).filter(
                User.job_title.in_(["HR", "Manager", "Director", "Founder & CEO", "CEO", "Managing Director"]),
                User.tenant_id == user.tenant_id,
                User.is_active == True,
                User.id != user.id
            ).all()
            assignees.extend(hr_managers)

            for assignee in assignees:
                TaskAutomationService._create_task(
                    db=db, 
                    tenant_id=user.tenant_id, # ✅ TENANT ISOLATION
                    user_id=assignee.id,
                    title=f"Renew Driver's License ({user.full_name})" if assignee.id != user.id else "Renew Your Driver's License",
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
            # Assign to Finance team in the SAME TENANT
            finance_team = db.query(User).filter(
                User.job_title.in_(["Accountant", "Credit Control", "Manager", "Cashier", "Director", "CEO", "Managing Director"]),
                User.tenant_id == invoice.tenant_id,
                User.is_active == True
            ).all()
            
            # Calculate days overdue safely
            if hasattr(invoice.due_date, 'date'):
                days_overdue = (today.date() - invoice.due_date.date()).days
            else:
                days_overdue = (today - invoice.due_date).days

            # Get amount safely (fallback to total_amount or amount)
            amount = getattr(invoice, 'total_amount', getattr(invoice, 'amount', 'N/A'))
            inv_number = getattr(invoice, 'invoice_number', getattr(invoice, 'id', 'Unknown'))
            
            for accountant in finance_team:
                TaskAutomationService._create_task(
                    db=db, 
                    tenant_id=invoice.tenant_id, # ✅ TENANT ISOLATION
                    user_id=accountant.id,
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
            # Safely get date fields (adjust names if your model uses different ones)
            next_service = getattr(vehicle, 'next_service_date', None)
            insurance_expiry = getattr(vehicle, 'insurance_expiry', None)
            plate = getattr(vehicle, 'plate_number', getattr(vehicle, 'license_plate', 'Vehicle'))
            
            # Fleet team assignment
            fleet_team = db.query(User).filter(
                User.job_title.in_(["Fleet Manager", "Manager", "Director", "Dispatcher", "CEO", "Managing Director"]),
                User.tenant_id == vehicle.tenant_id,
                User.is_active == True
            ).all()

            # A. Service Due
            if next_service and hasattr(next_service, 'date'):
                if next_service.date() >= today.date() and next_service.date() <= (today + timedelta(days=14)).date():
                    for manager in fleet_team:
                        TaskAutomationService._create_task(
                            db=db, 
                            tenant_id=vehicle.tenant_id, # ✅ TENANT ISOLATION
                            user_id=manager.id,
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
                    for manager in fleet_team:
                        TaskAutomationService._create_task(
                            db=db, 
                            tenant_id=vehicle.tenant_id, # ✅ TENANT ISOLATION
                            user_id=manager.id,
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
    def _create_task(
        db: Session, 
        tenant_id: int,  # ✅ CRITICAL FOR ISOLATION
        user_id: int, 
        title: str, 
        description: str, 
        category: str, 
        priority: TaskPriority, 
        due_date: datetime,
        target_type: str, 
        target_id: int
    ):
        """Helper to create a task if it doesn't already exist"""
        
        # ✅ SECURITY: Check for existing tasks WITHIN THE SAME TENANT
        existing = db.query(Task).filter(
            Task.tenant_id == tenant_id,
            Task.user_id == user_id,
            Task.target_type == target_type,
            Task.target_id == target_id,
            Task.status != TaskStatus.completed
        ).first()
        
        if not existing:
            task = Task(
                tenant_id=tenant_id, # ✅ STAMP WITH TENANT ID
                user_id=user_id, 
                title=title, 
                description=description,
                category=category, 
                priority=priority, 
                due_date=due_date,
                is_system_generated=True, 
                target_type=target_type, 
                target_id=target_id
            )
            db.add(task)

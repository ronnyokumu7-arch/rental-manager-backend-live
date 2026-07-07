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
        
        # 1. Expiring Driver's Licenses (HR/Admin Tasks)
        users_with_expiring_dl = db.query(User).filter(
            User.dl_expiry.between(today, today + timedelta(days=30)),
            User.is_active == True,
            User.dl_expiry != None
        ).all()
        
        for user in users_with_expiring_dl:
            days_left = (user.dl_expiry - today).days
            TaskAutomationService._create_task(
                db=db, user_id=user.id,
                title=f"Renew Driver's License",
                description=f"Your driver's license expires in {days_left} days. Please submit renewal documents.",
                category="compliance", priority="high" if days_left < 7 else "medium",
                due_date=user.dl_expiry - timedelta(days=7),
                target_type="user", target_id=user.id
            )
        
        # 2. Overdue Invoices (Finance Tasks)
        overdue_invoices = db.query(Invoice).filter(
            Invoice.status == "overdue",
            Invoice.due_date < today
        ).all()
        
        for invoice in overdue_invoices:
            accountants = db.query(User).filter(
                User.job_title.in_(["Accountant", "Credit Control", "Manager"]),
                User.tenant_id == invoice.tenant_id
            ).all()
            
            for accountant in accountants:
                TaskAutomationService._create_task(
                    db=db, user_id=accountant.id,
                    title=f"Follow up on Overdue Invoice #{invoice.invoice_number}",
                    description=f"Invoice is {(today - invoice.due_date).days} days overdue. Amount: {invoice.amount_due}",
                    category="finance", priority="high",
                    due_date=today + timedelta(days=3),
                    target_type="invoice", target_id=invoice.id
                )
        
        db.commit()

    @staticmethod
    def _create_task(db: Session, user_id: int, title: str, description: str, 
                     category: str, priority: TaskPriority, due_date: datetime,
                     target_type: str, target_id: int):
        """Helper to create a task if it doesn't already exist"""
        existing = db.query(Task).filter(
            Task.user_id == user_id,
            Task.target_type == target_type,
            Task.target_id == target_id,
            Task.status != TaskStatus.completed
        ).first()
        
        if not existing:
            task = Task(
                user_id=user_id, title=title, description=description,
                category=category, priority=priority, due_date=due_date,
                is_system_generated=True, target_type=target_type, target_id=target_id
            )
            db.add(task)

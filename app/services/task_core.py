# app/services/task_core.py
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.users import User

class TaskCoreService:
    """
    Core Task Routing Logic (Plan A / Plan B)
    Shared across all domain-specific task generators.
    """

    @staticmethod
    def smart_create_task(
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
        1. Checks for duplicates (same target AND same title).
        2. Plan A: Matches job_title -> Assigns to user (Status: pending).
        3. Plan B: No match -> Drops to pool (Status: unassigned).
        """
        # 1. Duplicate Check (Prevents spamming the DB)
        # ✅ FIX: Added Task.title == title so we can have multiple DIFFERENT tasks for the same booking/vehicle
        existing = db.query(Task).filter(
            Task.tenant_id == tenant_id,
            Task.target_type == target_type,
            Task.target_id == target_id,
            Task.title == title,
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

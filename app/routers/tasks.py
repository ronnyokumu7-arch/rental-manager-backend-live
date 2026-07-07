from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.users import User, UserRole
from app.models.task import Task, TaskStatus
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])

# The Bouncers: Only admins can manage the unassigned pool
admin_or_above = Depends(require_role([UserRole.super_admin, UserRole.tenant_admin]))

# ---------------------------------------------------------------------------
# 1. PERSONAL TASKS (For the individual user)
# ---------------------------------------------------------------------------
@router.get("/my-tasks", response_model=List[TaskOut])
def get_my_tasks(
    status: Optional[TaskStatus] = None,
    category: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch tasks specifically assigned to the current user."""
    query = db.query(Task).filter(
        Task.tenant_id == current_user.tenant_id,
        Task.user_id == current_user.id,
        Task.is_archived == False
    )
    
    if status: query = query.filter(Task.status == status)
    if category: query = query.filter(Task.category == category)
    
    tasks = query.order_by(Task.due_date.asc(), Task.priority.desc()).limit(limit).all()
    
    # Auto-update status dynamically based on due date
    now = datetime.now()
    for task in tasks:
        if task.status == TaskStatus.upcoming and task.due_date and task.due_date <= now:
            task.status = TaskStatus.pending
            
    db.commit()
    return tasks

# ---------------------------------------------------------------------------
# 2. THE UNASSIGNED POOL (For Admins/Managers to manage orphaned tasks)
# ---------------------------------------------------------------------------
@router.get("/unassigned", response_model=List[TaskOut])
def get_unassigned_tasks(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = admin_or_above # ✅ Admin only
):
    """Fetch tasks that have no user assigned (The Unassigned Pool)."""
    return db.query(Task).filter(
        Task.tenant_id == current_user.tenant_id,
        Task.user_id == None,
        Task.status == TaskStatus.unassigned,
        Task.is_archived == False
    ).order_by(Task.created_at.desc()).limit(limit).all()

# ---------------------------------------------------------------------------
# 3. TASK LIFECYCLE ACTIONS (Claim, Assign, Complete)
# ---------------------------------------------------------------------------
@router.patch("/{task_id}/claim", response_model=TaskOut)
def claim_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Allow a user to claim an unassigned task for themselves."""
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.tenant_id == current_user.tenant_id,
        Task.user_id == None,
        Task.status == TaskStatus.unassigned
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or already claimed")
        
    task.user_id = current_user.id
    task.status = TaskStatus.pending
    db.commit()
    db.refresh(task)
    return task

@router.patch("/{task_id}/assign", response_model=TaskOut)
def assign_task(
    task_id: int,
    payload: dict, # Expects {"user_id": 123}
    db: Session = Depends(get_db),
    current_user: User = admin_or_above
):
    """Allow an Admin to manually assign an unassigned task to a specific user."""
    if "user_id" not in payload:
        raise HTTPException(status_code=400, detail="user_id is required")
        
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.tenant_id == current_user.tenant_id,
        Task.user_id == None
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    target_user = db.query(User).filter(
        User.id == payload["user_id"],
        User.tenant_id == current_user.tenant_id
    ).first()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found in your agency")
        
    task.user_id = target_user.id
    task.status = TaskStatus.upcoming
    task.requires_role = None
    db.commit()
    db.refresh(task)
    return task

@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    task_update: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update task status (e.g., mark as completed)."""
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.tenant_id == current_user.tenant_id,
        Task.user_id == current_user.id
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    update_data = task_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)
    
    if task_update.status == TaskStatus.completed and not task.completed_at:
        task.completed_at = datetime.now()
    
    db.commit()
    db.refresh(task)
    return task

# ---------------------------------------------------------------------------
# 4. MANUAL CREATION & DELETION
# ---------------------------------------------------------------------------
@router.post("/", response_model=TaskOut)
def create_task(
    task: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Manually create a task. If no user_id is provided, it goes to the Unassigned Pool."""
    db_task = Task(
        **task.model_dump(), 
        tenant_id=current_user.tenant_id, 
        is_system_generated=False,
        created_by=current_user.id
    )
    
    if not db_task.user_id:
        db_task.status = TaskStatus.unassigned
        
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task

@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a task."""
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.tenant_id == current_user.tenant_id 
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.user_id != current_user.id and current_user.role not in [UserRole.tenant_admin, UserRole.super_admin]:
        raise HTTPException(status_code=403, detail="Not authorized to delete this task")
    
    db.delete(task)
    db.commit()

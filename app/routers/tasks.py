from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.models.task import Task, TaskStatus
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.get("/my-tasks", response_model=List[TaskOut])
def get_my_tasks(
    status: Optional[TaskStatus] = None,
    category: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get tasks for the current user"""
    query = db.query(Task).filter(Task.user_id == current_user.id)
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

@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    task_update: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update task status (complete, etc.)"""
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
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

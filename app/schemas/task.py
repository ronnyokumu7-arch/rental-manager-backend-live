from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models.task import TaskStatus, TaskPriority

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    category: str
    priority: TaskPriority = TaskPriority.medium
    due_date: Optional[datetime] = None
    target_type: Optional[str] = None
    target_id: Optional[int] = None

class TaskCreate(TaskBase):
    user_id: int
    is_system_generated: bool = True
    created_by: Optional[int] = None

class TaskUpdate(BaseModel):
    status: Optional[TaskStatus] = None
    completed_at: Optional[datetime] = None

class TaskOut(TaskBase):
    id: int
    user_id: int
    status: TaskStatus
    is_system_generated: bool
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}

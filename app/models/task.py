# app/models/task.py
import enum
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base

class TaskStatus(str, enum.Enum):
    unassigned = "unassigned"
    pending = "pending"
    completed = "completed"
    # ✅ 'upcoming' is completely removed to match your SQL update

class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"

class Task(Base):
    # ✅ CRITICAL FIX: Added the double underscores!
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # SECURITY & ISOLATION
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # FUTURE-PROOFING: Multi-branch support (Nullable for now)
    location_id = Column(Integer, nullable=True, index=True)
    
    # USER ASSIGNMENT & UNASSIGNED POOL
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # SMART ROUTING: Remembers what role this task was meant for if unassigned
    requires_role = Column(String(50), nullable=True)
    
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False)  # fleet, finance, hr, booking, compliance
    
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.pending)
    priority = Column(Enum(TaskPriority), default=TaskPriority.medium)
    
    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    is_system_generated = Column(Boolean, default=True)
    
    # DATA LIFECYCLE: For the 30-90 day archiving strategy
    is_archived = Column(Boolean, default=False, server_default="false")
    
    # Polymorphic references
    target_type = Column(String(50), nullable=True)  
    target_id = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # RELATIONSHIPS
    tenant = relationship("Tenant", backref="tasks")
    user = relationship("User", foreign_keys=[user_id], backref="assigned_tasks")
    creator = relationship("User", foreign_keys=[created_by])

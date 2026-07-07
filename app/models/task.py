import enum
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base

class TaskStatus(str, enum.Enum):
    upcoming = "upcoming"
    pending = "pending"
    completed = "completed"

class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False)  # fleet, finance, hr, booking, compliance
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.pending)
    priority = Column(Enum(TaskPriority), default=TaskPriority.medium)
    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    is_system_generated = Column(Boolean, default=True)
    target_type = Column(String(50), nullable=True)  # booking, invoice, vehicle, client, user
    target_id = Column(Integer, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", backref="tasks")
    creator = relationship("User", foreign_keys=[created_by])

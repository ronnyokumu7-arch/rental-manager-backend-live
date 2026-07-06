from sqlalchemy import Column, Integer, String, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.db.database import Base

class RoleTemplate(Base):
    __tablename__ = "role_templates"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # The job title this template applies to (e.g., "Driver", "Accountant")
    job_title = Column(String, nullable=False) 
    
    # The default permissions assigned to users with this job title
    permissions = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)

    tenant = relationship("Tenant", backref="role_templates")

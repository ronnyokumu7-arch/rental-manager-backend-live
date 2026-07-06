from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.dependencies.rbac import require_role
from app.models.users import User, UserRole
from app.models.role_template import RoleTemplate
from app.schemas.role_template import RoleTemplateOut, RoleTemplateUpdate
from app.core.permissions import PERMISSION_CATEGORIES

router = APIRouter(prefix="/role-templates", tags=["role_templates"])

@router.get("/matrix")
def get_permission_matrix(
    # ✅ FIX: Wrapped in Depends()
    current_user: User = Depends(require_role([UserRole.tenant_admin, UserRole.super_admin])),
):
    """Returns the master dictionary of all possible permissions for the UI to render."""
    return PERMISSION_CATEGORIES

@router.get("/", response_model=List[RoleTemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    # ✅ FIX: Wrapped in Depends()
    current_user: User = Depends(require_role([UserRole.tenant_admin, UserRole.super_admin])),
):
    """Returns all role templates for the current tenant."""
    return db.query(RoleTemplate).filter(RoleTemplate.tenant_id == current_user.tenant_id).all()

@router.patch("/{template_id}", response_model=RoleTemplateOut)
def update_template(
    template_id: int,
    payload: RoleTemplateUpdate,
    db: Session = Depends(get_db),
    # ✅ FIX: Wrapped in Depends()
    current_user: User = Depends(require_role([UserRole.tenant_admin, UserRole.super_admin])),
):
    """Updates the default permissions for a specific job title."""
    template = db.query(RoleTemplate).filter(
        RoleTemplate.id == template_id,
        RoleTemplate.tenant_id == current_user.tenant_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
        
    template.permissions = payload.permissions
    db.commit()
    db.refresh(template)
    return template

# app/routers/tenants/lifecycle.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.tenants import Tenant
from app.models.users import User, UserRole
from app.schemas.tenant import TenantOut

router = APIRouter()

super_admin_only = Depends(require_role([UserRole.super_admin]))


@router.post("/{tenant_id}/suspend", response_model=TenantOut)
def suspend_tenant(
    tenant_id: int,
    reason: str | None = "Administrative Action",
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    tenant = db.query(Tenant).options(joinedload(Tenant.profile)).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # ✅ FIX: Actually assign the reason to the model field
    tenant.is_active = False
    tenant.suspension_reason = reason
    db.commit()
    db.refresh(tenant)
    db.refresh(tenant.profile)
    return tenant


@router.post("/{tenant_id}/activate", response_model=TenantOut)
def activate_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    tenant = db.query(Tenant).options(joinedload(Tenant.profile)).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant.is_active = True
    tenant.suspension_reason = None  # Clear reason on reactivation
    db.commit()
    db.refresh(tenant)
    db.refresh(tenant.profile)
    return tenant


@router.post("/{tenant_id}/archive", response_model=TenantOut)
def archive_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    """Moves tenant to Vault (Soft Delete)"""
    tenant = db.query(Tenant).options(joinedload(Tenant.profile)).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant.is_archived = True
    tenant.is_active = False
    db.commit()
    db.refresh(tenant)
    db.refresh(tenant.profile)
    return tenant


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(
    tenant_id: int,
    hard_delete: bool = Query(False, description="Permanently remove from DB instead of archiving"),
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    if hard_delete:
        db.delete(tenant)
        db.commit()
    else:
        # Default behavior is soft delete / archive
        tenant.is_archived = True
        tenant.is_active = False
        db.commit()

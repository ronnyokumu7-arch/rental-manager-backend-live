# app/routers/users/_helpers.py
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.tenants import Tenant
from app.models.users import User, UserRole

# ---------------------------------------------------------------------------
# STRICT MATRIX ENFORCEMENT
# ---------------------------------------------------------------------------
VALID_ADMIN_TITLES = {"Director", "Manager", "HR"}

VALID_STAFF_DEPARTMENTS = {
    "Fleet & Operations": {"Fleet Manager", "Dispatcher", "Driver"},
    "Finance": {"Accountant", "Cashier"},
    "Sales & Contracts": {"Sales Agent", "Contracts Officer"},
}

def _validate_job_title_and_department(role: UserRole, department: str | None, job_title: str | None) -> None:
    if role == UserRole.super_admin:
        return

    if role == UserRole.tenant_admin:
        if job_title and job_title not in VALID_ADMIN_TITLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid admin title. Must be one of: {', '.join(VALID_ADMIN_TITLES)}")
    elif role == UserRole.tenant_staff:
        if not department or not job_title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Staff members must have both a department and a job title assigned.")
        if department not in VALID_STAFF_DEPARTMENTS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid department. Must be one of: {', '.join(VALID_STAFF_DEPARTMENTS.keys())}")
        if job_title not in VALID_STAFF_DEPARTMENTS[department]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid job title for department '{department}'.")

# ---------------------------------------------------------------------------
# Business Logic Helpers
# ---------------------------------------------------------------------------
def _get_user_or_404(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

def _validate_tenant_for_role(db: Session, role: UserRole, tenant_id: int | None) -> None:
    if role == UserRole.super_admin:
        return
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id is required for tenant users")
    tenant_exists = db.query(Tenant.id).filter(Tenant.id == tenant_id).first()
    if not tenant_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

def _enforce_create_permission(current_user: User, new_role: UserRole, new_tenant_id: int | None) -> None:
    if current_user.role == UserRole.super_admin:
        return
    if new_role == UserRole.super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admins cannot create super admin users")
    if new_tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admins can only create users within their own tenant")

def _enforce_update_permission(current_user: User, target_user: User, update_data: dict) -> None:
    if current_user.role == UserRole.super_admin:
        return
    if current_user.id == target_user.id:
        forbidden_fields = {"role", "tenant_id", "is_active", "permissions", "department", "job_title"}
        if forbidden_fields.intersection(update_data.keys()):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot change your own role, tenant, status, or permissions")
        return
    if target_user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admins can only update users within their own tenant")
    if target_user.role == UserRole.super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admins cannot update super admin users")

def _enforce_staff_permission(current_user: User, target_user: User, action: str) -> None:
    if current_user.role == UserRole.super_admin:
        return
    if target_user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Tenant admins can only {action} users within their own tenant")
    if target_user.role in (UserRole.super_admin, UserRole.tenant_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Tenant admins can only {action} tenant staff")

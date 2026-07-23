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
# Agency Owner Helper
# ---------------------------------------------------------------------------
def _is_agency_owner(user: User, db: Session) -> bool:
    """Checks if the user is the primary owner of their tenant."""
    if not user.tenant_id:
        return False
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    return tenant is not None and tenant.owner_id == user.id

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

# ✅ UPDATED: Added db: Session to check Agency Owner status
def _enforce_update_permission(current_user: User, target_user: User, update_data: dict, db: Session) -> None:
    # Super Admins can update anyone, anything
    if current_user.role == UserRole.super_admin:
        return

    # 1. SELF-UPDATE RULES
    if current_user.id == target_user.id:
        if current_user.role == UserRole.tenant_admin:
            # Tenant Admins can update everything about themselves except their tenant_id
            if "tenant_id" in update_data:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot change your own tenant ID")
        elif current_user.role == UserRole.tenant_staff:
            # Staff can ONLY update basic personal details
            allowed_fields = {"full_name", "email", "phone_number", "password"}
            requested_fields = set(update_data.keys())
            disallowed = requested_fields - allowed_fields
            if disallowed:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff members can only update their name, email, phone number, or password.")
        return

    # 2. CROSS-USER UPDATE RULES (Only Tenant Admins can update others)
    if current_user.role != UserRole.tenant_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Tenant Admins or Super Admins can update other users.")

    if target_user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admins can only update users within their own tenant")
    
    if target_user.role == UserRole.super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admins cannot update super admin users")

    # ✅ NEW: AGENCY OWNER PROTECTION
    # Regular Tenant Admins cannot modify the Agency Owner (unless they are the owner themselves, handled above)
    if _is_agency_owner(target_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot modify the Agency Owner's profile.")

# ✅ UPDATED: Added db: Session and removed blanket ban on tenant_admin
def _enforce_staff_permission(current_user: User, target_user: User, action: str, db: Session) -> None:
    if current_user.role == UserRole.super_admin:
        return
        
    if target_user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Tenant admins can only {action} users within their own tenant")
        
    # ✅ NEW: AGENCY OWNER PROTECTION
    # Block regular Tenant Admins from verifying/suspending/deleting the Agency Owner
    if _is_agency_owner(target_user, db) and current_user.id != target_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Only the Super Admin can {action} the Agency Owner.")
        
    # ✅ FIXED: Removed UserRole.tenant_admin from the blocked list.
    # Tenant Admins can now manage other Tenant Admins, provided they aren't the Agency Owner.
    if target_user.role == UserRole.super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Tenant admins cannot {action} super admin users")

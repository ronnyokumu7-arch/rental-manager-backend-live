# app/routers/users/management.py
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_password_hash, normalize_email
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.users import User, UserRole
from app.models.role_template import RoleTemplate
from app.models.tenants import Tenant
from app.core.permissions import ALL_PERMISSION_KEYS
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.email import send_welcome_email
from ._helpers import (
    _validate_job_title_and_department,
    _get_user_or_404,
    _validate_tenant_for_role,
    _enforce_create_permission,
    _enforce_update_permission,
    _is_agency_owner, # ✅ ADDED for delete protection
)

router = APIRouter() 

admin_or_above = Depends(require_role([UserRole.super_admin, UserRole.tenant_admin]))


# ✅ Helper to inject the is_tenant_owner flag without N+1 queries
def _enrich_users_with_owner_status(users: list[User], db: Session) -> list[User]:
    """Fetches owner IDs in bulk and attaches is_tenant_owner to user objects for Pydantic."""
    tenant_ids = list(set(u.tenant_id for u in users if u.tenant_id))
    owner_ids = set()
    
    if tenant_ids:
        owner_ids = {
            row[0] for row in db.query(Tenant.owner_id).filter(Tenant.id.in_(tenant_ids)).all() if row[0]
        }
        
    for u in users:
        u.is_tenant_owner = u.id in owner_ids
        
    return users


# =============================================================================
# 1. LIST USERS (GET /)
# =============================================================================
@router.get("/", response_model=list[UserOut])
def list_users(
    tenant_id: int | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    is_suspended: bool | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), # ✅ FIX: Allow any authenticated user to list users
):
    """List users with optional filtering. Strict tenant isolation enforced."""
    query = db.query(User)
    
    # ✅ FIX: Super admins can see all (or filter by tenant_id). Everyone else sees only their tenant.
    if current_user.role == UserRole.super_admin:
        if tenant_id is not None:
            query = query.filter(User.tenant_id == tenant_id)
    else:
        # Tenant admins and staff can only see users in their own tenant
        query = query.filter(User.tenant_id == current_user.tenant_id)
        
    if role is not None:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if is_suspended is not None:
        query = query.filter(User.is_suspended == is_suspended)
        
    users = query.order_by(User.created_at.desc()).all()
    enriched_users = _enrich_users_with_owner_status(users, db)
    
    def sort_key(u):
        is_owner = 0 if getattr(u, 'is_tenant_owner', False) else 1
        ts = u.created_at.timestamp() if u.created_at else 0
        return (is_owner, -ts)
        
    enriched_users.sort(key=sort_key)
    return enriched_users


# =============================================================================
# 2. GET SINGLE USER (GET /{user_id})
# =============================================================================
@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), # ✅ FIX: Allow any authenticated user to hit this endpoint
):
    """Retrieve a single user by ID. Allows self-viewing for all roles."""
    user = _get_user_or_404(user_id, db)
    
    # 1. SELF-VIEW BYPASS: Any user can view their own profile
    if current_user.id == user.id:
        return _enrich_users_with_owner_status([user], db)[0]
        
    # 2. CROSS-USER VIEWING: Only admins can view others
    if current_user.role not in [UserRole.super_admin, UserRole.tenant_admin]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    # 3. TENANT ISOLATION: Admins can only view users in their own tenant
    if current_user.role == UserRole.tenant_admin and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    return _enrich_users_with_owner_status([user], db)[0]


# =============================================================================
# 3. UPDATE USER (PATCH /{user_id})
# =============================================================================
@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    update_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = admin_or_above,
):
    """Update user details. Enforces strict permission and validation rules."""
    user = _get_user_or_404(user_id, db)
    
    _enforce_update_permission(current_user, user, update_data.model_dump(exclude_unset=True), db)
    
    safe_update_data = update_data.model_dump(exclude_unset=True)
    
    if "email" in safe_update_data:
        new_email = normalize_email(safe_update_data["email"])
        existing_user = db.query(User).filter(User.email == new_email, User.id != user_id).first()
        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use")
        safe_update_data["email"] = new_email

    if "password" in safe_update_data:
        safe_update_data["password_hash"] = get_password_hash(safe_update_data.pop("password"))
        safe_update_data["failed_login_attempts"] = 0
        safe_update_data["account_locked_until"] = None

    if "role" in safe_update_data or "tenant_id" in safe_update_data:
        new_role = safe_update_data.get("role", user.role)
        new_tenant_id = safe_update_data.get("tenant_id", user.tenant_id)
        _validate_tenant_for_role(db, new_role, new_tenant_id)
        _enforce_create_permission(current_user, new_role, new_tenant_id)

    if "job_title" in safe_update_data or "department" in safe_update_data:
        _validate_job_title_and_department(
            safe_update_data.get("role", user.role),
            safe_update_data.get("department", user.department),
            safe_update_data.get("job_title", user.job_title)
        )

    for field, value in safe_update_data.items():
        setattr(user, field, value)
        
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Update failed due to database constraint")
        
    db.refresh(user)
    return _enrich_users_with_owner_status([user], db)[0]


# =============================================================================
# 4. CREATE USER (POST /)
# =============================================================================
@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = admin_or_above,
):
    user_data = user.model_dump(exclude={"password"})
    user_data["email"] = normalize_email(user_data["email"])
    
    if user.role != UserRole.super_admin and not user_data.get("tenant_id"):
        user_data["tenant_id"] = current_user.tenant_id

    _validate_job_title_and_department(user.role, user_data.get("department"), user_data.get("job_title"))
    _enforce_create_permission(current_user, user.role, user_data.get("tenant_id"))
    _validate_tenant_for_role(db, user.role, user_data.get("tenant_id"))

    if user.role == UserRole.super_admin:
        user_data["tenant_id"] = None

    if user.password:
        db_user = User(
            **user_data, 
            password_hash=get_password_hash(user.password), 
            is_onboarded=True,
            email_verified=True 
        )
    else:
        invite_token = secrets.token_urlsafe(32)
        invite_expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
        db_user = User(
            **user_data, 
            password_hash=None, 
            invite_token=invite_token, 
            invite_expires_at=invite_expires_at, 
            is_onboarded=False,
            email_verified=False
        )
    
    if user_data.get("job_title"):
        template = db.query(RoleTemplate).filter(
            RoleTemplate.tenant_id == user_data["tenant_id"],
            RoleTemplate.job_title == user_data["job_title"]
        ).first()
        if template:
            db_user.permissions = template.permissions
        elif user.role == UserRole.tenant_admin:
            db_user.permissions = ALL_PERMISSION_KEYS
        else:
            db_user.permissions = ["view_dashboard", "view_bookings", "view_clients"]
    elif user.role == UserRole.tenant_admin:
        db_user.permissions = ALL_PERMISSION_KEYS
    else:
        db_user.permissions = ["view_dashboard", "view_bookings", "view_clients"]

    db.add(db_user)
    db.flush()
    
    is_agency_owner = False
    temp_password = None
    if current_user.role == UserRole.super_admin and db_user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == db_user.tenant_id).first()
        if tenant and tenant.owner_id is None:
            is_agency_owner = True
            tenant.owner_id = db_user.id
            
            if not user.password:
                temp_password = secrets.token_urlsafe(12)
                db_user.password_hash = get_password_hash(temp_password)
            
            db_user.is_onboarded = True
            db_user.email_verified = True
            db_user.phone_verified = True
            db_user.invite_token = None
            db_user.invite_expires_at = None

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A user with this email already exists")
        
    db.refresh(db_user)
    
    if is_agency_owner and not user.password:
        send_welcome_email(to=db_user.email, full_name=db_user.full_name, role=db_user.role.value, temp_password=temp_password)
    elif not user.password:
        invite_link = f"https://your-app-domain.com/invite?token={db_user.invite_token}"
        send_welcome_email(to=db_user.email, full_name=db_user.full_name, role=db_user.role.value, temp_password=invite_link)
    else:
        send_welcome_email(to=db_user.email, full_name=db_user.full_name, role=db_user.role.value, temp_password=user.password)
    
    return _enrich_users_with_owner_status([db_user], db)[0]


# =============================================================================
# 5. DELETE USER (DELETE /{user_id}) ✅ NEW
# =============================================================================
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = admin_or_above,
):
    """Delete a user. Enforces strict permission and Agency Owner protection."""
    user = _get_user_or_404(user_id, db)
    
    # 1. Enforce Deletion Permissions
    if current_user.role == UserRole.super_admin:
        pass # Super admins can delete anyone
    elif current_user.role == UserRole.tenant_admin:
        if user.tenant_id != current_user.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admins can only delete users within their own tenant")
        
        # ✅ AGENCY OWNER PROTECTION
        if _is_agency_owner(user, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="You cannot delete the Agency Owner. Only a Super Admin can remove the primary tenant owner."
            )
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Tenant Admins or Super Admins can delete users.")
        
    # 2. Prevent self-deletion
    if current_user.id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account. Please contact a Super Admin.")

    # 3. Perform deletion
    db.delete(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Deletion failed due to database constraints (e.g., user has associated records like bookings or payments)."
        )
        
    return None

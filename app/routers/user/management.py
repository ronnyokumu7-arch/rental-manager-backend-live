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
)

router = APIRouter() 

admin_or_above = Depends(require_role([UserRole.super_admin, UserRole.tenant_admin]))


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
    current_user: User = admin_or_above,
):
    """List users with optional filtering. Strict tenant isolation enforced."""
    query = db.query(User)
    
    # Enforce Tenant Isolation
    if current_user.role == UserRole.tenant_admin:
        query = query.filter(User.tenant_id == current_user.tenant_id)
    elif current_user.role == UserRole.super_admin and tenant_id is not None:
        query = query.filter(User.tenant_id == tenant_id)
        
    # Apply Optional Filters
    if role is not None:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if is_suspended is not None:
        query = query.filter(User.is_suspended == is_suspended)
        
    return query.order_by(User.created_at.desc()).all()


# =============================================================================
# 2. GET SINGLE USER (GET /{user_id})
# =============================================================================
@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = admin_or_above,
):
    """Retrieve a single user by ID."""
    user = _get_user_or_404(user_id, db)
    
    # Tenant admins can only view users in their own tenant
    if current_user.role == UserRole.tenant_admin and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    return user


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
    
    # 1. Enforce Update Permissions (Self-update vs Cross-user update rules)
    _enforce_update_permission(current_user, user, update_data.model_dump(exclude_unset=True))
    
    # 2. Process Updates safely
    safe_update_data = update_data.model_dump(exclude_unset=True)
    
    # Handle Email Update (Normalize and check uniqueness)
    if "email" in safe_update_data:
        new_email = normalize_email(safe_update_data["email"])
        existing_user = db.query(User).filter(User.email == new_email, User.id != user_id).first()
        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use")
        safe_update_data["email"] = new_email

    # Handle Password Update (Hash it)
    if "password" in safe_update_data:
        safe_update_data["password_hash"] = get_password_hash(safe_update_data.pop("password"))

    # Handle Role/Tenant Validation if they are being updated
    if "role" in safe_update_data or "tenant_id" in safe_update_data:
        new_role = safe_update_data.get("role", user.role)
        new_tenant_id = safe_update_data.get("tenant_id", user.tenant_id)
        _validate_tenant_for_role(db, new_role, new_tenant_id)
        _enforce_create_permission(current_user, new_role, new_tenant_id)

    # Handle Job Title / Department Validation
    if "job_title" in safe_update_data or "department" in safe_update_data:
        _validate_job_title_and_department(
            safe_update_data.get("role", user.role),
            safe_update_data.get("department", user.department),
            safe_update_data.get("job_title", user.job_title)
        )

    # 3. Apply and Commit
    for field, value in safe_update_data.items():
        setattr(user, field, value)
        
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Update failed due to database constraint")
        
    db.refresh(user)
    return user


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

    # Handle Invite Mode (No Password) vs Direct Create (With Password)
    if user.password:
        db_user = User(**user_data, password_hash=get_password_hash(user.password), is_onboarded=True)
    else:
        invite_token = secrets.token_urlsafe(32)
        invite_expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
        db_user = User(
            **user_data, 
            password_hash=None, 
            invite_token=invite_token, 
            invite_expires_at=invite_expires_at, 
            is_onboarded=False
        )
    
    # Assign Permissions based on Role Template or Defaults
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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A user with this email already exists")
        
    db.refresh(db_user)
    
    # Send Invite Email or Welcome Email
    if not user.password:
        # Note: Replace with your actual frontend domain
        invite_link = f"https://your-app-domain.com/invite?token={db_user.invite_token}"
        send_welcome_email(
            to=db_user.email,
            full_name=db_user.full_name,
            role=db_user.role.value,
            temp_password=invite_link, 
        )
    else:
        send_welcome_email(
            to=db_user.email,
            full_name=db_user.full_name,
            role=db_user.role.value,
            temp_password=user.password,
        )
    
    return db_user

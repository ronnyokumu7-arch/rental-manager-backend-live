# app/routers/users/management.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_password_hash, normalize_email
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.users import User, UserRole
from app.models.role_template import RoleTemplate
from app.core.permissions import ALL_PERMISSION_KEYS
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.email import send_welcome_email, send_password_changed
from ._helpers import (
    _validate_job_title_and_department,
    _get_user_or_404,
    _validate_tenant_for_role,
    _enforce_create_permission,
    _enforce_update_permission,
)

router = APIRouter()

admin_or_above = Depends(require_role([UserRole.super_admin, UserRole.tenant_admin]))

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

    db_user = User(**user_data, password_hash=get_password_hash(user.password))
    
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
    
    send_welcome_email(
        to=db_user.email,
        full_name=db_user.full_name,
        role=db_user.role.value,
        temp_password=user.password,
    )
    
    return db_user

@router.get("/", response_model=list[UserOut])
def list_users(
    tenant_id: int | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    is_suspended: bool | None = None,
    db: Session = Depends(get_db),
    current_user: User = admin_or_above,
):
    query = db.query(User)
    
    # ✅ FIX: Super admins see ALL users unless a specific tenant_id is requested
    if current_user.role == UserRole.super_admin:
        if tenant_id:
            query = query.filter(User.tenant_id == tenant_id)
    else:
        query = query.filter(User.tenant_id == current_user.tenant_id)
        
    if role is not None:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if is_suspended is not None:
        query = query.filter(User.is_suspended == is_suspended)
        
    return query.order_by(User.created_at.desc()).all()

@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = _get_user_or_404(user_id, db)
    if current_user.role == UserRole.super_admin or current_user.id == user_id:
        return user
    if current_user.role == UserRole.tenant_admin and user.tenant_id == current_user.tenant_id:
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to view this user")

@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = _get_user_or_404(user_id, db)
    update_data = user_update.model_dump(exclude_unset=True)
    
    sensitive_fields = {"role", "permissions", "department", "job_title", "is_active"}
    if sensitive_fields.intersection(update_data.keys()) and current_user.role not in [UserRole.super_admin, UserRole.tenant_admin]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can update roles, permissions, or department assignments.")
        
    if "email" in update_data and update_data["email"] is not None:
        update_data["email"] = normalize_email(update_data["email"])
        
    _enforce_update_permission(current_user, user, update_data)
    
    new_role = update_data.get("role", user.role)
    new_department = update_data.get("department", user.department)
    new_job_title = update_data.get("job_title", user.job_title)
    
    _validate_job_title_and_department(new_role, new_department, new_job_title)
    
    new_tenant_id = update_data.get("tenant_id", user.tenant_id)
    _validate_tenant_for_role(db, new_role, new_tenant_id)
    
    if new_role == UserRole.super_admin:
        update_data["tenant_id"] = None
        
    password = update_data.pop("password", None)
    if password is not None:
        user.password_hash = get_password_hash(password)
        
    for field, value in update_data.items():
        setattr(user, field, value)
        
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A user with this email already exists")
        
    db.refresh(user)
    
    if password is not None:
        send_password_changed(to=user.email, full_name=user.full_name)
        
    return user

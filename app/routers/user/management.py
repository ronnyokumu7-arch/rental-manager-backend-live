# app/routers/users/management.py
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# ... (keep your existing imports) ...

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

    # ✅ NEW: Handle Invite Mode (No Password) vs Direct Create (With Password)
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
    
    # ... (keep the rest of your role/permission assignment logic exactly as is) ...
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
    
    # ✅ NEW: Send Invite Email instead of Welcome Email with temp password if no password was provided
    if not user.password:
        invite_link = f"https://your-app-domain.com/invite?token={db_user.invite_token}"
        send_welcome_email(
            to=db_user.email,
            full_name=db_user.full_name,
            role=db_user.role.value,
            temp_password=invite_link, # Reusing temp_password param to send the link
        )
    else:
        send_welcome_email(
            to=db_user.email,
            full_name=db_user.full_name,
            role=db_user.role.value,
            temp_password=user.password,
        )
    
    return db_user

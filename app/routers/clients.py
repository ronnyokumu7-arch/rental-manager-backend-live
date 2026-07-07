from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.clients import Client, ClientStatus
from app.models.users import User
from app.models.task import TaskPriority # ✅ NEW: Import TaskPriority
from app.schemas.client import ClientCreate, ClientOut, ClientUpdate
from app.services.storage import upload_file, delete_file
from app.services.task_automation import TaskAutomationService # ✅ NEW: Import Automation Service

router = APIRouter(prefix="/clients", tags=["clients"])

# ---------------------------------------------------------------------------
# TASK DISPATCHER HELPER (Client Onboarding Engine)
# ---------------------------------------------------------------------------
def _dispatch_client_tasks(client: Client, action: str, db: Session):
    """Generates tasks based on client lifecycle events using Smart Routing."""
    tenant_id = client.tenant_id
    now = datetime.now(timezone.utc)
    
    if action == "created":
        # Task 1: Verify ID
        TaskAutomationService._smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Sales Agent",
            title=f"Verify ID Documents for {client.full_name}",
            description=f"New client onboarded. Please verify their ID documents.",
            category="compliance", priority=TaskPriority.high,
            due_date=now + timedelta(hours=24),
            target_type="client", target_id=client.id
        )
        # Task 2: Verify DL
        TaskAutomationService._smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Sales Agent",
            title=f"Verify Driver's License for {client.full_name}",
            description=f"New client onboarded. Please verify their Driver's License.",
            category="compliance", priority=TaskPriority.high,
            due_date=now + timedelta(hours=24),
            target_type="client", target_id=client.id
        )
        
    elif action == "document_uploaded":
        TaskAutomationService._smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Sales Agent",
            title=f"Review Uploaded Documents for {client.full_name}",
            description=f"Client has uploaded new identification documents. Please review and approve.",
            category="compliance", priority=TaskPriority.high,
            due_date=now + timedelta(hours=12),
            target_type="client", target_id=client.id
        )
        
    elif action == "suspended":
        TaskAutomationService._smart_create_task(
            db=db, tenant_id=tenant_id, target_role="Manager",
            title=f"Review Suspended Client: {client.full_name}",
            description=f"Client has been suspended. Review reason and notify sales team if necessary.",
            category="compliance", priority=TaskPriority.medium,
            due_date=now + timedelta(hours=24),
            target_type="client", target_id=client.id
        )

# ---------------------------------------------------------------------------
# Business Logic Helpers
# ---------------------------------------------------------------------------
def _get_client_or_404(client_id: int, tenant_id: int, db: Session) -> Client:
    """Helper to retrieve a client or raise 404 if not found or unauthorized."""
    client = db.query(Client).filter(
        Client.id == client_id,
        Client.tenant_id == tenant_id,
    ).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    return client

def _handle_unique_constraint_error(e: IntegrityError, field_name: str) -> None:
    """Convert SQLAlchemy IntegrityError into a user-friendly HTTPException."""
    error_msg = str(e.orig).lower()
    if "uq_tenant_phone" in error_msg:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A client with this phone number already exists",
        )
    if "uq_tenant_id_number" in error_msg:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A client with this ID number already exists",
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"A client with this {field_name} already exists",
    )

# ---------------------------------------------------------------------------
# Routes — List & Search
# ---------------------------------------------------------------------------
@router.get("/", response_model=list[ClientOut])
def read_clients(
    search: Optional[str] = Query(None, description="Search by name, email, or phone"),
    status_filter: Optional[ClientStatus] = Query(
        None, alias="status", description="Filter by status"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all active (non-archived) clients for the current tenant.
    Supports search and status filtering.
    """
    query = db.query(Client).filter(
        Client.tenant_id == current_user.tenant_id,
        Client.is_archived == False,
    )
    
    # Search across name, email, phone
    if search:
        q = f"%{search}%"
        query = query.filter(
            or_(
                Client.full_name.ilike(q),
                Client.email.ilike(q),
                Client.phone.ilike(q),
            )
        )
    
    # Status filter
    if status_filter is not None:
        query = query.filter(Client.status == status_filter)
        
    return query.order_by(Client.created_at.desc()).all()

@router.get("/archived", response_model=list[ClientOut])
def read_archived_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all archived clients for the current tenant."""
    return (
        db.query(Client)
        .filter(
            Client.tenant_id == current_user.tenant_id,
            Client.is_archived == True,
        )
        .order_by(Client.archived_at.desc())
        .all()
    )

# ---------------------------------------------------------------------------
# Routes — CRUD
# ---------------------------------------------------------------------------
@router.post("/", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    client: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """Create a new client. Phone must be unique per tenant."""
    db_client = Client(**client.model_dump(), tenant_id=current_user.tenant_id)
    db.add(db_client)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        _handle_unique_constraint_error(
            db.execute("SELECT 1").close() or Exception(), "phone"
        )
    db.refresh(db_client)
    
    # ✅ TRIGGER: Client Created
    _dispatch_client_tasks(db_client, "created", db)
    
    return db_client

@router.get("/{client_id}", response_model=ClientOut)
def read_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single client by ID."""
    return _get_client_or_404(client_id, current_user.tenant_id, db)

@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    updates: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """
    Update a client's details.
    Cannot update archived clients.
    """
    client = _get_client_or_404(client_id, current_user.tenant_id, db)
    if client.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archived clients cannot be edited. Restore them first.",
        )
    
    update_data = updates.model_dump(exclude_unset=True)
    
    # Prevent status changes via PATCH — use dedicated endpoints
    if "status" in update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use the dedicated status endpoints (suspend/reactivate) to change status.",
        )
        
    for field, value in update_data.items():
        setattr(client, field, value)
        
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        _handle_unique_constraint_error(Exception(), "phone or ID number")
        
    db.refresh(client)
    return client

@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """
    Permanently delete a client.
    Cannot delete clients with active bookings.
    """
    client = _get_client_or_404(client_id, current_user.tenant_id, db)
    
    # Check for active bookings
    active_bookings = (
        db.query(client.bookings)
        .filter(client.bookings.any(status="active"))
        .first()
    )
    if active_bookings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a client with active bookings. Cancel or complete them first.",
        )
        
    # Delete associated files
    for field in ["avatar_image", "id_image_front", "id_image_back", "dl_image_front"]:
        url = getattr(client, field, None)
        if url:
            delete_file(url)
            
    db.delete(client)
    db.commit()

# ---------------------------------------------------------------------------
# Routes — Status Transitions
# ---------------------------------------------------------------------------
@router.post("/{client_id}/suspend", response_model=ClientOut)
def suspend_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """
    Suspend a client. They will not be able to make new bookings.
    Only active clients can be suspended.
    """
    client = _get_client_or_404(client_id, current_user.tenant_id, db)
    if client.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archived clients cannot be suspended. Restore them first.",
        )
    if client.status == ClientStatus.suspended:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client is already suspended",
        )
    if client.status != ClientStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only active clients can be suspended. Current status: '{client.status.value}'",
        )
        
    client.status = ClientStatus.suspended
    db.commit()
    db.refresh(client)
    
    # ✅ TRIGGER: Client Suspended
    _dispatch_client_tasks(client, "suspended", db)
    
    return client

@router.post("/{client_id}/reactivate", response_model=ClientOut)
def reactivate_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """
    Reactivate a client (from suspended, pending, or inactive).
    Sets status to 'active'.
    """
    client = _get_client_or_404(client_id, current_user.tenant_id, db)
    if client.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archived clients cannot be reactivated. Restore them first.",
        )
    if client.status == ClientStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client is already active",
        )
        
    client.status = ClientStatus.active
    db.commit()
    db.refresh(client)
    return client

# ---------------------------------------------------------------------------
# Routes — Archive Workflow
# ---------------------------------------------------------------------------
@router.post("/{client_id}/archive", response_model=ClientOut)
def archive_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """
    Archive a client. They will be hidden from the active list.
    Cannot archive clients with active bookings.
    """
    client = _get_client_or_404(client_id, current_user.tenant_id, db)
    if client.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client is already archived",
        )
        
    # Check for active bookings
    has_active = any(
        b.status.value == "active" for b in client.bookings
    )
    if has_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot archive a client with active bookings. Complete or cancel them first.",
        )
        
    client.is_archived = True
    client.archived_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(client)
    return client

@router.post("/{client_id}/restore", response_model=ClientOut)
def restore_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """Restore an archived client. They reappear in the active list."""
    client = _get_client_or_404(client_id, current_user.tenant_id, db)
    if not client.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client is not archived",
        )
        
    client.is_archived = False
    client.archived_at = None
    db.commit()
    db.refresh(client)
    return client

# ---------------------------------------------------------------------------
# Routes — File Uploads
# ---------------------------------------------------------------------------
@router.post("/{client_id}/upload/avatar", response_model=ClientOut)
async def upload_client_avatar(
    client_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """Upload or replace the client's avatar image."""
    client = _get_client_or_404(client_id, current_user.tenant_id, db)
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image",
        )
        
    # Delete old avatar if exists
    if client.avatar_image:
        delete_file(client.avatar_image)
        
    # Upload new file
    url = await upload_file(file, folder=f"clients/{client.tenant_id}/{client_id}/avatar")
    client.avatar_image = url
    db.commit()
    db.refresh(client)
    return client

@router.post("/{client_id}/upload/id-document", response_model=ClientOut)
async def upload_id_document(
    client_id: int,
    front: UploadFile = File(...),
    back: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """Upload ID document images (front required, back optional)."""
    client = _get_client_or_404(client_id, current_user.tenant_id, db)
    
    for file in [front, back]:
        if file and (not file.content_type or not file.content_type.startswith("image/")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Files must be images",
            )
            
    # Delete old images
    if client.id_image_front:
        delete_file(client.id_image_front)
    if client.id_image_back:
        delete_file(client.id_image_back)
        
    folder = f"clients/{client.tenant_id}/{client_id}/id"
    
    # Upload front
    client.id_image_front = await upload_file(front, folder=folder)
    
    # Upload back (if provided)
    if back:
        client.id_image_back = await upload_file(back, folder=folder)
        
    db.commit()
    db.refresh(client)
    
    # ✅ TRIGGER: Document Uploaded
    _dispatch_client_tasks(client, "document_uploaded", db)
    
    return client

@router.post("/{client_id}/upload/dl-document", response_model=ClientOut)
async def upload_dl_document(
    client_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """Upload driver's license image."""
    client = _get_client_or_404(client_id, current_user.tenant_id, db)
    
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image",
        )
        
    # Delete old DL image
    if client.dl_image_front:
        delete_file(client.dl_image_front)
        
    url = await upload_file(file, folder=f"clients/{client.tenant_id}/{client_id}/dl")
    client.dl_image_front = url
    db.commit()
    db.refresh(client)
    
    # ✅ TRIGGER: Document Uploaded
    _dispatch_client_tasks(client, "document_uploaded", db)
    
    return client

# app/routers/clients.py
import os
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.users import User
from app.models.clients import Client, ClientStatus
from app.schemas.client import ClientCreate, ClientOut, ClientUpdate
from app.services.client_tasks import ClientTaskService

router = APIRouter(prefix="/clients", tags=["clients"])

def _get_authorized_client(client_id: int, user: User, db: Session) -> Client:
    client = db.query(Client).filter(
        Client.id == client_id,
        Client.tenant_id == user.tenant_id
    ).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client

def _save_upload_file(file: UploadFile, client_id: int, prefix: str) -> str:
    """Helper to securely save uploaded files and return the relative path."""
    ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
    unique_filename = f"{prefix}_{secrets.token_hex(4)}{ext}"
    
    directory = f"./uploads/clients/{client_id}"
    os.makedirs(directory, exist_ok=True)
    
    file_path = os.path.join(directory, unique_filename)
    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())
        
    # Return relative path for database storage
    return f"uploads/clients/{client_id}/{unique_filename}"

# ---------------------------------------------------------------------------
# CORE CRUD
# ---------------------------------------------------------------------------

@router.post("/", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    client: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    # Check for duplicate phone or ID number within the tenant
    existing_phone = db.query(Client).filter(
        Client.tenant_id == current_user.tenant_id, 
        Client.phone == client.phone
    ).first()
    if existing_phone:
        raise HTTPException(400, "A client with this phone number already exists.")

    if client.id_number:
        existing_id = db.query(Client).filter(
            Client.tenant_id == current_user.tenant_id, 
            Client.id_number == client.id_number
        ).first()
        if existing_id:
            raise HTTPException(400, "A client with this ID number already exists.")

    db_client = Client(**client.model_dump(), tenant_id=current_user.tenant_id)
    db.add(db_client)
    db.commit()
    db.refresh(db_client)

    # ⚡ EVENT TRIGGER: Check for missing docs and pending verification
    ClientTaskService.check_compliance_on_create(db, db_client, db_client.tenant_id)

    return db_client

@router.get("/", response_model=list[ClientOut])
def list_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    return db.query(Client).filter(
        Client.tenant_id == current_user.tenant_id,
        Client.is_archived == False,
    ).order_by(Client.created_at.desc()).all()

@router.get("/archived", response_model=list[ClientOut])
def list_archived_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    return db.query(Client).filter(
        Client.tenant_id == current_user.tenant_id,
        Client.is_archived == True,
    ).order_by(Client.archived_at.desc()).all()

@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    return _get_authorized_client(client_id, current_user, db)

@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    updates: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    client = _get_authorized_client(client_id, current_user, db)
    update_data = updates.model_dump(exclude_unset=True)

    # Prevent changing phone to an existing one
    if "phone" in update_data and update_data["phone"] != client.phone:
        existing = db.query(Client).filter(
            Client.tenant_id == current_user.tenant_id,
            Client.phone == update_data["phone"],
            Client.id != client_id
        ).first()
        if existing:
            raise HTTPException(400, "Phone number already in use by another client.")

    for field, value in update_data.items():
        setattr(client, field, value)

    db.commit()
    db.refresh(client)

    # ⚡ EVENT TRIGGER: If DL expiry was updated, check if it's now expired or near expiry
    if "dl_expiry" in update_data:
        ClientTaskService.check_dl_expiry(db, client, client.tenant_id)

    return client

# ---------------------------------------------------------------------------
# DOCUMENT UPLOADS (⚡ TRIGGERS COMPLIANCE RE-EVALUATION)
# ---------------------------------------------------------------------------

@router.post("/{client_id}/upload-id-front", response_model=ClientOut)
def upload_id_front(
    client_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    client = _get_authorized_client(client_id, current_user, db)
    client.id_image_front = _save_upload_file(file, client_id, "id_front")
    db.commit()
    db.refresh(client)
    
    # ⚡ EVENT TRIGGER: Re-evaluate missing documents
    ClientTaskService.check_compliance_on_create(db, client, client.tenant_id)
    return client

@router.post("/{client_id}/upload-id-back", response_model=ClientOut)
def upload_id_back(
    client_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    client = _get_authorized_client(client_id, current_user, db)
    client.id_image_back = _save_upload_file(file, client_id, "id_back")
    db.commit()
    db.refresh(client)
    
    ClientTaskService.check_compliance_on_create(db, client, client.tenant_id)
    return client

@router.post("/{client_id}/upload-dl-front", response_model=ClientOut)
def upload_dl_front(
    client_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    client = _get_authorized_client(client_id, current_user, db)
    client.dl_image_front = _save_upload_file(file, client_id, "dl_front")
    db.commit()
    db.refresh(client)
    
    # ⚡ EVENT TRIGGER: Re-evaluate missing docs AND check DL expiry
    ClientTaskService.check_compliance_on_create(db, client, client.tenant_id)
    ClientTaskService.check_dl_expiry(db, client, client.tenant_id)
    return client

@router.post("/{client_id}/upload-avatar", response_model=ClientOut)
def upload_avatar(
    client_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    client = _get_authorized_client(client_id, current_user, db)
    client.avatar_image = _save_upload_file(file, client_id, "avatar")
    db.commit()
    db.refresh(client)
    return client

# ---------------------------------------------------------------------------
# LIFECYCLE TRANSITIONS
# ---------------------------------------------------------------------------

@router.post("/{client_id}/activate", response_model=ClientOut)
def activate_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    client = _get_authorized_client(client_id, current_user, db)
    if client.status == ClientStatus.active:
        raise HTTPException(400, "Client is already active.")
    
    # Compliance gate: Cannot activate if critical docs are missing
    if not client.id_image_front or not client.dl_image_front:
        raise HTTPException(400, "Cannot activate client. ID and DL photos are required.")
        
    client.status = ClientStatus.active
    db.commit()
    db.refresh(client)
    return client

@router.post("/{client_id}/suspend", response_model=ClientOut)
def suspend_client(
    client_id: int,
    reason: str = "Violation of terms",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    client = _get_authorized_client(client_id, current_user, db)
    if client.status == ClientStatus.suspended:
        raise HTTPException(400, "Client is already suspended.")
        
    client.status = ClientStatus.suspended
    db.commit()
    db.refresh(client)
    return client

@router.post("/{client_id}/reactivate", response_model=ClientOut)
def reactivate_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    client = _get_authorized_client(client_id, current_user, db)
    if client.status != ClientStatus.suspended:
        raise HTTPException(400, "Only suspended clients can be reactivated.")
        
    client.status = ClientStatus.active
    db.commit()
    db.refresh(client)
    return client

# ---------------------------------------------------------------------------
# ARCHIVE & DELETE
# ---------------------------------------------------------------------------

@router.post("/{client_id}/archive", response_model=ClientOut)
def archive_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    client = _get_authorized_client(client_id, current_user, db)
    if client.is_archived:
        raise HTTPException(400, "Client is already archived.")
        
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
    client = _get_authorized_client(client_id, current_user, db)
    if not client.is_archived:
        raise HTTPException(400, "Client is not archived.")
        
    client.is_archived = False
    client.archived_at = None
    db.commit()
    db.refresh(client)
    return client

@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    client = _get_authorized_client(client_id, current_user, db)
    if client.is_archived == False:
        raise HTTPException(400, "Client must be archived before deletion.")
        
    db.delete(client)
    db.commit()

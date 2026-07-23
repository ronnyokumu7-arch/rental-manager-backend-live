# backend/app/routers/contracts/management.py (or your actual contracts router file)
import base64
import os
from datetime import datetime, timedelta, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.bookings import Booking
from app.models.clients import Client
from app.models.contracts import Contract, ContractStatus
from app.models.tenants import Tenant
from app.models.users import User
from app.models.vehicles import Vehicle
from app.schemas.contract import ContractOut, PublicContractView, ContractSignPayload
from app.services.contracts import create_contract_for_booking
from app.services.contract_pdf import generate_contract_pdf
from app.services.email import send_contract_to_client

router = APIRouter(prefix="/contracts", tags=["contracts"])

# ---------------------------------------------------------------------------
# Business Logic Helpers
# ---------------------------------------------------------------------------

def _get_contract_or_404(contract_id: int, tenant_id: int, db: Session) -> Contract:
    contract = db.query(Contract).filter(
        Contract.id == contract_id,
        Contract.tenant_id == tenant_id,
    ).first()
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found"
        )
    return contract

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[ContractOut])
def list_contracts(
    booking_id: int | None = None,
    contract_status: ContractStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ✅ UPDATED: Eagerly load 'booking' AND 'client' so computed fields can access them
    query = db.query(Contract).options(
        joinedload(Contract.booking).joinedload(Booking.client)
    ).filter(Contract.tenant_id == current_user.tenant_id)
    
    if booking_id is not None:
        query = query.filter(Contract.booking_id == booking_id)
    if contract_status is not None:
        query = query.filter(Contract.status == contract_status)
        
    return query.order_by(Contract.created_at.desc()).all()

@router.get("/{contract_id}", response_model=ContractOut)
def get_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ✅ Also eager load here for consistency
    contract = db.query(Contract).options(
        joinedload(Contract.booking).joinedload(Booking.client)
    ).filter(
        Contract.id == contract_id,
        Contract.tenant_id == current_user.tenant_id,
    ).first()
    
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found"
        )
    return contract

@router.get("/{contract_id}/pdf")
def download_contract_pdf(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = _get_contract_or_404(contract_id, current_user.tenant_id, db)
    pdf_bytes = generate_contract_pdf(contract, db)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=contract-{contract.contract_number}.pdf"
        },
    )

@router.post("/{contract_id}/void", response_model=ContractOut)
def void_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    contract = _get_contract_or_404(contract_id, current_user.tenant_id, db)
    if contract.status == ContractStatus.void:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contract is already void")
    if contract.status == ContractStatus.signed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Signed contracts cannot be voided")
        
    contract.status = ContractStatus.void
    db.commit()
    db.refresh(contract)
    return contract

@router.post("/bookings/{booking_id}/regenerate", response_model=ContractOut)
def regenerate_contract(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.tenant_id == current_user.tenant_id,
    ).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        
    existing = db.query(Contract).filter(Contract.booking_id == booking_id).first()
    if existing:
        db.delete(existing)
        db.commit()
        
    return create_contract_for_booking(booking, db)

@router.post("/{contract_id}/share-link", response_model=dict)
def generate_share_link(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    contract = _get_contract_or_404(contract_id, current_user.tenant_id, db)
    if contract.status == ContractStatus.void:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Void contracts cannot be shared")

    share_token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    contract.share_token = share_token
    contract.share_token_expires_at = expires_at
    
    # ✅ FIX: Only change status to "sent" if it is currently a "draft"
    if contract.status == ContractStatus.draft:
        contract.status = ContractStatus.sent

    db.commit()
    db.refresh(contract)

    base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    share_url = f"{base_url}/contracts/view/{share_token}"

    return {
        "share_token": share_token,
        "share_url": share_url,
        "expires_at": expires_at
    }

@router.post("/{contract_id}/send-to-client", response_model=ContractOut)
def send_contract_to_client_endpoint(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    contract = _get_contract_or_404(contract_id, current_user.tenant_id, db)
    booking = db.query(Booking).filter(Booking.id == contract.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    client = db.query(Client).filter(Client.id == booking.client_id).first()
    if not client or not client.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Client email not available")

    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()

    if not contract.share_token:
        share_token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        contract.share_token = share_token
        contract.share_token_expires_at = expires_at

    contract.status = ContractStatus.sent
    db.commit()
    db.refresh(contract)

    base_url = "http://localhost:3000" # Update to your frontend URL
    share_url = f"{base_url}/contracts/view/{contract.share_token}"

    send_contract_to_client(
        to=client.email,
        client_name=client.full_name,
        contract_number=contract.contract_number,
        vehicle=f"{vehicle.make} {vehicle.model} ({vehicle.plate_number})",
        start_date=str(booking.start_date),
        end_date=str(booking.end_date),
        total_amount=str(booking.total_amount),
        currency=booking.currency_code,
        contract_url=share_url,
    )

    return contract

@router.get("/public/{token}", response_model=PublicContractView)
def view_contract_public(
    token: str,
    db: Session = Depends(get_db),
):
    contract = db.query(Contract).filter(Contract.share_token == token).first()
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    if contract.share_token_expires_at and contract.share_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This contract link has expired.")

    booking = db.query(Booking).filter(Booking.id == contract.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    client = db.query(Client).filter(Client.id == booking.client_id).first()
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first()
    tenant = db.query(Tenant).filter(Tenant.id == booking.tenant_id).first()

    return PublicContractView(
        contract_number=contract.contract_number,
        booking_id=booking.id,
        tenant_name=tenant.name if tenant else "Unknown",
        client_name=client.full_name if client else "Unknown",
        vehicle_make=vehicle.make if vehicle else "Unknown",
        vehicle_model=vehicle.model if vehicle else "Unknown",
        vehicle_plate=vehicle.plate_number if vehicle else "Unknown",
        start_date=str(booking.start_date),
        end_date=str(booking.end_date),
        total_amount=str(booking.total_amount),
        currency_code=booking.currency_code,
        status=contract.status,
        signed_by_client=contract.signed_by_client,
        created_at=contract.created_at,
    )

@router.get("/public/{token}/pdf")
def download_contract_pdf_public(
    token: str,
    db: Session = Depends(get_db),
):
    contract = db.query(Contract).filter(Contract.share_token == token).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if contract.share_token_expires_at and contract.share_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This contract link has expired")

    pdf_bytes = generate_contract_pdf(contract, db)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=contract-{contract.contract_number}.pdf"
        },
    )

@router.post("/public/{token}/sign", response_model=dict)
def sign_contract_public(
    token: str,
    payload: ContractSignPayload,
    db: Session = Depends(get_db),
):
    contract = db.query(Contract).filter(Contract.share_token == token).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if contract.share_token_expires_at and contract.share_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This contract link has expired")

    if contract.status == ContractStatus.void:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This contract has been voided")

    if contract.signed_by_client:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contract already signed")

    now = datetime.now(timezone.utc)
    
    # ✅ NEW: Process and save the signature image
    if payload.signature:
        try:
            # Strip the data URI prefix if present (e.g., "data:image/png;base64,")
            signature_data = payload.signature.split(",")[1] if "," in payload.signature else payload.signature
            image_bytes = base64.b64decode(signature_data)
            
            # Define storage path
            signature_dir = "storage/signatures"
            os.makedirs(signature_dir, exist_ok=True)
            
            # Create a unique filename
            filename = f"sig_{contract.id}_{int(now.timestamp())}.png"
            filepath = os.path.join(signature_dir, filename)
            
            # Save the file
            with open(filepath, "wb") as f:
                f.write(image_bytes)
                
            # Link the path to the contract model
            contract.signature_image_path = filepath
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to process signature: {str(e)}")

    # Update contract status
    contract.signed_by_client = True
    contract.client_signed_at = now
    contract.status = ContractStatus.signed

    db.commit()
    db.refresh(contract)

    return {
        "message": "Contract signed successfully",
        "contract_number": contract.contract_number,
        "signed_at": now.isoformat()
    }

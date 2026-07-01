# backend/app/routers/quotations.py
import os
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.bookings import Booking, BookingStatus
from app.models.clients import Client
from app.models.quotations import Quotation, QuotationStatus
from app.models.tenants import Tenant
from app.models.users import User
from app.models.vehicles import Vehicle
from app.schemas.quotation import QuotationCreate, QuotationOut, QuotationPublicView
from app.services.contracts import create_contract_for_booking
from app.services.invoices import create_invoice_for_booking

router = APIRouter(prefix="/quotations", tags=["quotations"])

@router.get("/", response_model=list[QuotationOut])
def list_quotations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    return db.query(Quotation).filter(
        Quotation.tenant_id == current_user.tenant_id
    ).order_by(Quotation.created_at.desc()).all()

@router.get("/{quotation_id}", response_model=QuotationOut)
def get_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    quotation = db.query(Quotation).filter(
        Quotation.id == quotation_id,
        Quotation.tenant_id == current_user.tenant_id,
    ).first()
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return quotation

@router.post("/", response_model=QuotationOut, status_code=status.HTTP_201_CREATED)
def create_quotation(
    data: QuotationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    quotation = Quotation(
        **data.model_dump(),
        tenant_id=current_user.tenant_id,
        status=QuotationStatus.pending,
    )
    db.add(quotation)
    db.commit()
    db.refresh(quotation)
    return quotation

@router.post("/{quotation_id}/share-link", response_model=dict)
def generate_share_link(
    quotation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    quotation = db.query(Quotation).filter(
        Quotation.id == quotation_id,
        Quotation.tenant_id == current_user.tenant_id,
    ).first()
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status != QuotationStatus.pending:
        raise HTTPException(status_code=400, detail="Can only share pending quotations")
    
    if not quotation.share_token:
        quotation.share_token = str(uuid.uuid4())
        quotation.share_token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        db.commit()

    base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return {
        "share_url": f"{base_url}/quote/{quotation.share_token}",
        "share_token": quotation.share_token,
        "expires_at": quotation.share_token_expires_at,
    }

@router.get("/public/{token}", response_model=QuotationPublicView)
def view_public_quotation(token: str, db: Session = Depends(get_db)):
    quotation = db.query(Quotation).filter(Quotation.share_token == token).first()
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.share_token_expires_at and quotation.share_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This quotation has expired")

    client = db.query(Client).filter(Client.id == quotation.client_id).first()
    vehicle = db.query(Vehicle).filter(Vehicle.id == quotation.vehicle_id).first()
    tenant = db.query(Tenant).filter(Tenant.id == quotation.tenant_id).first()

    return QuotationPublicView(
        id=quotation.id,
        tenant_name=tenant.name if tenant else "Unknown Agency",
        client_name=client.full_name if client else "Valued Client",
        vehicle_details=f"{vehicle.make} {vehicle.model} ({vehicle.plate_number})" if vehicle else "Unknown Vehicle",
        start_date=str(quotation.start_date),
        end_date=str(quotation.end_date),
        pickup_location=quotation.pickup_location,
        return_location=quotation.return_location,
        destination=quotation.destination,
        daily_rate=str(quotation.daily_rate) if quotation.daily_rate else "0",
        total_amount=str(quotation.total_amount),
        currency_code=quotation.currency_code,
        terms_and_conditions=quotation.terms_and_conditions,
        status=quotation.status.value,
        expires_at=str(quotation.share_token_expires_at) if quotation.share_token_expires_at else None,
    )

@router.post("/public/{token}/accept")
def accept_quotation(token: str, db: Session = Depends(get_db)):
    quotation = db.query(Quotation).filter(Quotation.share_token == token).first()
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status != QuotationStatus.pending:
        raise HTTPException(status_code=400, detail="Quotation already processed")
        
    if quotation.share_token_expires_at and quotation.share_token_expires_at < datetime.now(timezone.utc):
        quotation.status = QuotationStatus.expired
        db.commit()
        raise HTTPException(status_code=410, detail="This quotation has expired")

    quotation.status = QuotationStatus.accepted
    
    if quotation.booking_id:
        booking = db.query(Booking).filter(Booking.id == quotation.booking_id).first()
        # ✅ Safety check: Only confirm if booking is still pending
        if booking and booking.status == BookingStatus.pending:
            booking.status = BookingStatus.confirmed
            create_contract_for_booking(booking, db)
            create_invoice_for_booking(booking, db)

    db.commit()
    return {"message": "Quotation accepted. Booking confirmed."}

@router.post("/public/{token}/decline")
def decline_quotation(token: str, db: Session = Depends(get_db)):
    quotation = db.query(Quotation).filter(Quotation.share_token == token).first()
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status != QuotationStatus.pending:
        raise HTTPException(status_code=400, detail="Quotation already processed")

    quotation.status = QuotationStatus.declined
    
    if quotation.booking_id:
        booking = db.query(Booking).filter(Booking.id == quotation.booking_id).first()
        # ✅ Safety check: Only cancel if booking is still pending
        if booking and booking.status == BookingStatus.pending:
            booking.status = BookingStatus.cancelled

    db.commit()
    return {"message": "Quotation declined."}

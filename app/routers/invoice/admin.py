import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, joinedload # ✅ Added joinedload

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.bookings import Booking
from app.models.invoices import Invoice, InvoiceStatus
from app.models.users import User
from app.schemas.invoice import InvoiceCreate, InvoiceOut, InvoiceUpdate
from app.services.invoices import create_invoice_for_booking
from app.services.invoice_pdf import generate_invoice_pdf

router = APIRouter()


@router.get("/", response_model=list[InvoiceOut])
def list_invoices(
    status_filter: Optional[InvoiceStatus] = Query(None, alias="status"),
    booking_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    # ✅ Eagerly load booking AND client to prevent N+1 queries and populate computed fields
    query = db.query(Invoice).options(
        joinedload(Invoice.booking).joinedload(Booking.client)
    ).filter(Invoice.tenant_id == current_user.tenant_id)
    
    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    if booking_id is not None:
        query = query.filter(Invoice.booking_id == booking_id)
        
    return query.order_by(Invoice.created_at.desc()).all()


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    # ✅ Also eager load here for consistency if the profile page needs it
    invoice = db.query(Invoice).options(
        joinedload(Invoice.booking).joinedload(Booking.client)
    ).filter(
        Invoice.id == invoice_id,
        Invoice.tenant_id == current_user.tenant_id
    ).first()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.post("/", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    booking = db.query(Booking).filter(
        Booking.id == payload.booking_id,
        Booking.tenant_id == current_user.tenant_id
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or access denied")

    invoice = create_invoice_for_booking(
        booking,
        db,
        custom_amount=payload.amount_due,
        custom_currency=payload.currency_code,
        discount_amount=payload.discount_amount,
        discount_reason=payload.discount_reason,
        due_date_override=payload.due_date,
        notes=payload.notes,
    )
    return invoice


@router.patch("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: int,
    updates: InvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.tenant_id == current_user.tenant_id
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status in (InvoiceStatus.paid, InvoiceStatus.void) and updates.amount_due is not None:
        raise HTTPException(status_code=400, detail="Cannot modify amount of a paid or void invoice")

    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(invoice, field, value)

    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/void", response_model=InvoiceOut)
def void_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.tenant_id == current_user.tenant_id
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == InvoiceStatus.void:
        raise HTTPException(status_code=400, detail="Invoice is already void")
    if invoice.status == InvoiceStatus.paid:
        raise HTTPException(status_code=400, detail="Cannot void a paid invoice")

    invoice.status = InvoiceStatus.void
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.tenant_id == current_user.tenant_id
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    pdf_bytes = generate_invoice_pdf(invoice, db)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Invoice_{invoice.invoice_number}.pdf"},
    )


@router.post("/{invoice_id}/share-link", response_model=dict)
def generate_invoice_share_link(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.tenant_id == current_user.tenant_id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    share_token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    invoice.share_token = share_token
    invoice.share_token_expires_at = expires_at

    db.commit()
    db.refresh(invoice)

    base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return {
        "share_token": share_token,
        "share_url": f"{base_url}/invoice/{share_token}",
        "expires_at": expires_at.isoformat(),
    }

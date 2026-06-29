import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.bookings import Booking
from app.models.clients import Client
from app.models.invoices import Invoice, InvoiceStatus
from app.models.tenants import Tenant
from app.models.users import User
from app.models.vehicles import Vehicle
from app.schemas.invoice import InvoiceCreate, InvoiceOut, InvoiceUpdate
from app.services.invoices import create_invoice_for_booking
from app.services.pdf import generate_invoice_pdf

router = APIRouter(prefix="/invoices", tags=["invoices"])

# ---------------------------------------------------------------------------
# LIST INVOICES
# ---------------------------------------------------------------------------
@router.get("/", response_model=list[InvoiceOut])
def list_invoices(
    status_filter: Optional[InvoiceStatus] = Query(None, alias="status"),
    booking_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    query = db.query(Invoice).filter(Invoice.tenant_id == current_user.tenant_id)
    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    if booking_id is not None:
        query = query.filter(Invoice.booking_id == booking_id)
    return query.order_by(Invoice.created_at.desc()).all()

# ---------------------------------------------------------------------------
# GET SINGLE INVOICE
# ---------------------------------------------------------------------------
@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
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
    return invoice

# ---------------------------------------------------------------------------
# CREATE INVOICE (Manual Override)
# ---------------------------------------------------------------------------
@router.post("/", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    from app.models.bookings import Booking
    booking = db.query(Booking).filter(
        Booking.id == payload.booking_id,
        Booking.tenant_id == current_user.tenant_id
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or access denied")
    
    if payload.notes:
        booking._override_notes = payload.notes 

    return create_invoice_for_booking(booking, db)

# ---------------------------------------------------------------------------
# UPDATE INVOICE
# ---------------------------------------------------------------------------
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
        
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(invoice, field, value)

    db.commit()
    db.refresh(invoice)
    return invoice

# ---------------------------------------------------------------------------
# VOID INVOICE
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# DOWNLOAD PDF (Private - Admin)
# ---------------------------------------------------------------------------
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
        
    # Generate on the fly to ensure it's always up to date
    pdf_bytes = generate_invoice_pdf(invoice, db)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Invoice_{invoice.invoice_number}.pdf"},
    )

# ---------------------------------------------------------------------------
# GENERATE SHARE LINK (New - For Customer Portal)
# ---------------------------------------------------------------------------
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
        "expires_at": expires_at,
    }

# ---------------------------------------------------------------------------
# PUBLIC: VIEW INVOICE (New - For Customer Portal)
# ---------------------------------------------------------------------------
@router.get("/public/{token}")
def view_invoice_public(token: str, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.share_token == token).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    if invoice.share_token_expires_at and invoice.share_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This invoice link has expired")

    # Fetch related data for the frontend
    booking = db.query(Booking).filter(Booking.id == invoice.booking_id).first() if invoice.booking_id else None
    client = db.query(Client).filter(Client.id == booking.client_id).first() if booking else None
    vehicle = db.query(Vehicle).filter(Vehicle.id == booking.vehicle_id).first() if booking and booking.vehicle_id else None
    tenant = db.query(Tenant).filter(Tenant.id == invoice.tenant_id).first()

    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "status": invoice.status.value,
        "amount_due": float(invoice.amount_due),
        "amount_paid": float(invoice.amount_paid),
        "currency_code": invoice.currency_code,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        "client_name": client.full_name if client else "Valued Client",
        "tenant_name": tenant.name if tenant else "Unknown Agency",
        "booking_details": {
            "vehicle": f"{vehicle.make} {vehicle.model} ({vehicle.plate_number})" if vehicle else "N/A",
            "start_date": str(booking.start_date) if booking else None,
            "end_date": str(booking.end_date) if booking else None,
        } if booking else None,
    }

# ---------------------------------------------------------------------------
# PUBLIC: DOWNLOAD PDF (New - For Customer Portal)
# ---------------------------------------------------------------------------
@router.get("/public/{token}/pdf")
def download_invoice_pdf_public(token: str, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.share_token == token).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    if invoice.share_token_expires_at and invoice.share_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This invoice link has expired")

    # Generate PDF on the fly
    pdf_bytes = generate_invoice_pdf(invoice, db)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Invoice_{invoice.invoice_number}.pdf"},
    )

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.bookings import Booking
from app.models.clients import Client
from app.models.invoices import Invoice, InvoiceStatus
from app.models.tenants import Tenant
from app.models.vehicles import Vehicle
from app.services.invoice_pdf import generate_invoice_pdf

router = APIRouter()


@router.get("/public/{token}")
def view_invoice_public(token: str, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.share_token == token).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.share_token_expires_at and invoice.share_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This invoice link has expired")

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
        "remaining_balance": float(max(0, invoice.amount_due - (invoice.amount_paid or 0))),
        "currency_code": invoice.currency_code,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        "discount_amount": float(invoice.discount_amount or 0),
        "discount_reason": invoice.discount_reason,
        "client_name": client.full_name if client else "Valued Client",
        "tenant_name": tenant.name if tenant else "Unknown Agency",
        "booking_details": {
            "vehicle": f"{vehicle.make} {vehicle.model} ({vehicle.plate_number})" if vehicle else "N/A",
            "start_date": str(booking.start_date) if booking else None,
            "end_date": str(booking.end_date) if booking else None,
        } if booking else None,
    }


@router.get("/public/{token}/pdf")
def download_invoice_pdf_public(token: str, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.share_token == token).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.share_token_expires_at and invoice.share_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This invoice link has expired")

    pdf_bytes = generate_invoice_pdf(invoice, db)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Invoice_{invoice.invoice_number}.pdf"},
    )

from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.models.bookings import Booking
from app.models.invoices import Invoice, InvoiceStatus

def _generate_invoice_number(tenant_id: int, db: Session) -> str:
    prefix = f"T{tenant_id}-"
    tenant_invoices = db.query(Invoice).filter(
        Invoice.tenant_id == tenant_id,
        Invoice.invoice_number.like(f"{prefix}%")
    ).all()
    max_seq = 0
    for inv in tenant_invoices:
        try:
            seq_part = inv.invoice_number.split('-')[1]
            max_seq = max(max_seq, int(seq_part))
        except (IndexError, ValueError):
            continue
    next_seq = max_seq + 1
    return f"{prefix}{next_seq:03d}"

def create_invoice_for_booking(
    booking: Booking, 
    db: Session, 
    custom_amount: Optional[Decimal] = None, 
    custom_currency: Optional[str] = None
) -> Invoice:
    existing_invoice = db.query(Invoice).filter(Invoice.booking_id == booking.id).first()

    if existing_invoice:
        return existing_invoice

    invoice_number = _generate_invoice_number(booking.tenant_id, db)

    final_amount = custom_amount if custom_amount is not None else booking.total_amount
    final_currency = custom_currency if custom_currency else (booking.currency_code or "KES")

    db_invoice = Invoice(
        tenant_id=booking.tenant_id,
        booking_id=booking.id,
        invoice_number=invoice_number,
        status=InvoiceStatus.draft,
        amount_due=final_amount,
        amount_paid=0,
        currency_code=final_currency,
        due_date=booking.end_date,
        notes=f"Auto-generated invoice for Booking #{booking.id}",
    )
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

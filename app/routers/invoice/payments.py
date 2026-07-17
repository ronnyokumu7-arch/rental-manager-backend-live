from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.invoices import Invoice, InvoiceStatus
from app.models.payments import Payment, PaymentStatus
from app.models.users import User
from app.schemas.payment import PaymentCreate, PaymentOut

router = APIRouter()


@router.post("/{invoice_id}/record-payment", response_model=PaymentOut)
def record_offline_payment(
    invoice_id: int,
    payload: PaymentCreate,
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
        raise HTTPException(status_code=400, detail="Cannot record payment against a void invoice")
    if invoice.status == InvoiceStatus.paid:
        raise HTTPException(status_code=400, detail="Invoice is already fully paid")

    remaining = (invoice.amount_due or Decimal("0")) - (invoice.amount_paid or Decimal("0"))
    if payload.amount > remaining:
        raise HTTPException(status_code=400, detail=f"Amount exceeds remaining balance of {remaining}")

    now = datetime.now(timezone.utc)

    db_payment = Payment(
        invoice_id=invoice.id,
        tenant_id=current_user.tenant_id,
        amount=payload.amount,
        currency_code=payload.currency_code,
        method=payload.method,
        reference=payload.reference,
        status=PaymentStatus.completed,
        paid_at=now,
        recorded_by=current_user.id,
        notes=payload.notes,
    )
    db.add(db_payment)

    new_paid = (invoice.amount_paid or Decimal("0")) + payload.amount
    invoice.amount_paid = new_paid

    if new_paid >= (invoice.amount_due or Decimal("0")):
        invoice.status = InvoiceStatus.paid
        invoice.paid_at = now
    elif new_paid > Decimal("0"):
        invoice.status = InvoiceStatus.partially_paid

    db.commit()
    db.refresh(db_payment)
    return db_payment

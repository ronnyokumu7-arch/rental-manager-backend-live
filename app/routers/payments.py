# backend/app/routers/payments/management.py (or your actual payments router file)
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.subscription import require_active_subscription
from app.models.bookings import Booking
from app.models.invoices import Invoice, InvoiceStatus
from app.models.payments import Payment, PaymentMethod, PaymentStatus
from app.models.users import User
from app.schemas.payment import PaymentCreate, PaymentOut, PaymentVoid

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/", response_model=list[PaymentOut])
def list_payments(
    invoice_id: Optional[int] = Query(None),
    status_filter: Optional[PaymentStatus] = Query(None, alias="status"),
    method_filter: Optional[PaymentMethod] = Query(None, alias="method"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    # ✅ Eagerly load the relationship chain so Pydantic computed fields can access client/invoice data
    query = db.query(Payment).options(
        joinedload(Payment.invoice)
        .joinedload(Invoice.booking)
        .joinedload(Booking.client)
    ).filter(Payment.tenant_id == current_user.tenant_id)

    if invoice_id is not None:
        query = query.filter(Payment.invoice_id == invoice_id)
    if status_filter is not None:
        query = query.filter(Payment.status == status_filter)
    if method_filter is not None:
        query = query.filter(Payment.method == method_filter)

    # ✅ Return SQLAlchemy objects directly. Pydantic will automatically map them 
    # and evaluate the @computed_field properties (invoice_number, client_id, client_name).
    return query.order_by(Payment.created_at.desc()).all()


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    # ✅ Eager load for the dedicated ops page / single payment view
    payment = db.query(Payment).options(
        joinedload(Payment.invoice)
        .joinedload(Invoice.booking)
        .joinedload(Booking.client)
    ).filter(
        Payment.id == payment_id,
        Payment.tenant_id == current_user.tenant_id
    ).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    return payment


@router.post("/{payment_id}/void", response_model=PaymentOut)
def void_payment(
    payment_id: int,
    payload: PaymentVoid,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    payment = db.query(Payment).filter(
        Payment.id == payment_id,
        Payment.tenant_id == current_user.tenant_id
    ).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status == PaymentStatus.void:
        raise HTTPException(status_code=400, detail="Payment is already void")
    if payment.status != PaymentStatus.completed:
        raise HTTPException(status_code=400, detail="Only completed payments can be voided")

    invoice = db.query(Invoice).filter(Invoice.id == payment.invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Linked invoice not found")

    original_paid = invoice.amount_paid or Decimal("0")
    new_paid = max(Decimal("0"), original_paid - payment.amount)

    invoice.amount_paid = new_paid

    if invoice.status == InvoiceStatus.paid and new_paid < (invoice.amount_due or Decimal("0")):
        invoice.status = InvoiceStatus.partially_paid
    elif new_paid <= Decimal("0"):
        invoice.status = InvoiceStatus.sent

    payment.status = PaymentStatus.void
    payment.notes = f"VOIDED by admin {current_user.id}: {payload.reason}"

    db.commit()
    db.refresh(payment)
    return payment


@router.get("/export/csv")
def export_payments_csv(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    # For CSV export, the manual join is actually more efficient than joinedload 
    # since we are building a flat list of strings anyway.
    query = db.query(Payment, Invoice.invoice_number).join(
        Invoice, Payment.invoice_id == Invoice.id
    ).filter(Payment.tenant_id == current_user.tenant_id)

    if start_date:
        query = query.filter(Payment.created_at >= start_date)
    if end_date:
        query = query.filter(Payment.created_at <= end_date)

    results = query.order_by(Payment.created_at.desc()).all()

    headers = ["ID", "Invoice Number", "Amount", "Currency", "Method", "Reference", "Status", "Recorded By", "Date"]
    rows = [
        [
            str(p.id),
            inv_num or "",
            str(p.amount),
            p.currency_code,
            p.method.value,
            p.reference or "",
            p.status.value,
            str(p.recorded_by or ""),
            p.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        ]
        for p, inv_num in results
    ]

    csv_content = "\n".join([",".join(headers)] + [",".join(row) for row in rows])

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=payments_export.csv"},
    )

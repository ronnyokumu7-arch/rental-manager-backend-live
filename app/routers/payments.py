from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.dependencies.subscription import require_active_subscription # NEW IMPORT
from app.models.invoices import Invoice, InvoiceStatus
from app.models.payments import Payment, PaymentStatus
from app.models.tenants import Tenant
from app.models.users import User, UserRole
from app.schemas.payment import PaymentCreate, PaymentOut
from app.services.email import send_payment_received

router = APIRouter(prefix="/payments", tags=["payments"])

super_admin_only = Depends(require_role([UserRole.super_admin]))

# ... (keep _get_authorized_payment helper) ...

@router.post("/", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def record_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription), # CHANGED from super_admin_only
):
    # Ensure the tenant owns the invoice they are paying
    invoice = db.query(Invoice).filter(
        Invoice.id == payload.invoice_id,
        Invoice.tenant_id == current_user.tenant_id
    ).first()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found or access denied")
        
    if invoice.status == InvoiceStatus.void:
        raise HTTPException(status_code=400, detail="Cannot record payment against a void invoice")
    if invoice.status == InvoiceStatus.paid:
        raise HTTPException(status_code=400, detail="Invoice is already fully paid")

    now = datetime.now(timezone.utc)

    db_payment = Payment(
        invoice_id=payload.invoice_id,
        tenant_id=current_user.tenant_id, # Inject from auth
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

    invoice.amount_paid = (invoice.amount_paid or 0) + payload.amount
    if invoice.amount_paid >= invoice.amount_due:
        invoice.status = InvoiceStatus.paid
        invoice.paid_at = now

    db.commit()
    db.refresh(db_payment)

    # Send receipt (Optional: you might want to send this to the Client instead of the Tenant if it's a booking payment, 
    # but for now we keep the existing tenant receipt logic).
    tenant = db.query(Tenant).filter(Tenant.id == db_payment.tenant_id).first()
    if tenant:
        send_payment_received(
            to=tenant.email,
            company_name=tenant.name,
            invoice_number=invoice.invoice_number,
            amount_paid=str(payload.amount),
            currency=payload.currency_code,
        )
        
    return db_payment

@router.get("/", response_model=list[PaymentOut])
def list_payments(
    invoice_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription), # CHANGED
):
    query = db.query(Payment).filter(Payment.tenant_id == current_user.tenant_id)
    if invoice_id is not None:
        query = query.filter(Payment.invoice_id == invoice_id)
    return query.order_by(Payment.created_at.desc()).all()

# ... (keep get_payment endpoint but change bouncer to require_active_subscription) ...

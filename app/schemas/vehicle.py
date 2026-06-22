backend/app/models/invoices.py

# Add this column below subscription_id
booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True, index=True)

# Add this relationship below subscription
booking = relationship("Booking", back_populates="invoices")




backend/app/models/bookings.py

# Add this relationship below contract
invoices = relationship("Invoice", back_populates="booking", cascade="all, delete-orphan")




backend/app/schemas/invoice.py

from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel
from app.models.invoices import InvoiceStatus

class InvoiceCreate(BaseModel):
    booking_id: Optional[int] = None       # NEW: Link to booking
    subscription_id: Optional[int] = None  # Keep for super-admin subscription billing
    amount_due: Decimal
    currency_code: str = "KES"
    due_date: datetime
    notes: Optional[str] = None

class InvoiceUpdate(BaseModel):
    amount_due: Optional[Decimal] = None
    currency_code: Optional[str] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = None

class InvoiceOut(BaseModel):
    id: int
    tenant_id: int
    booking_id: Optional[int] = None       # NEW
    subscription_id: Optional[int] = None
    invoice_number: str
    status: InvoiceStatus
    amount_due: Decimal
    amount_paid: Decimal
    currency_code: str
    due_date: datetime
    paid_at: Optional[datetime] = None
    pdf_path: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
    
    
    
    
    backend/app/routers/invoices.py
    
    from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.dependencies.subscription import require_active_subscription # NEW IMPORT
from app.models.bookings import Booking                             # NEW IMPORT
from app.models.invoices import Invoice, InvoiceStatus
from app.models.tenants import Tenant
from app.models.users import User, UserRole
from app.schemas.invoice import InvoiceCreate, InvoiceOut, InvoiceUpdate
from app.services.email import send_invoice_notification
from app.services.pdf import generate_invoice_pdf

router = APIRouter(prefix="/invoices", tags=["invoices"])

super_admin_only = Depends(require_role([UserRole.super_admin]))

# ... (keep _get_authorized_invoice and _generate_invoice_number helpers as they are) ...

@router.post("/", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription), # CHANGED from super_admin_only
):
    # If linking to a booking, verify the tenant owns the booking
    if payload.booking_id:
        booking = db.query(Booking).filter(
            Booking.id == payload.booking_id,
            Booking.tenant_id == current_user.tenant_id
        ).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found or access denied")

    invoice_number = _generate_invoice_number(current_user.tenant_id, db)
    
    db_invoice = Invoice(
        **payload.model_dump(),
        tenant_id=current_user.tenant_id, # Inject tenant_id from auth
        invoice_number=invoice_number,
        status=InvoiceStatus.draft,
        amount_paid=Decimal("0"),
    )
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

@router.patch("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: int,
    payload: InvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription), # CHANGED
):
    invoice = _get_authorized_invoice(invoice_id, current_user, db)
    if invoice.status in (InvoiceStatus.paid, InvoiceStatus.void):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit a {invoice.status.value} invoice",
        )
        
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(invoice, field, value)
        
    db.commit()
    db.refresh(invoice)
    return invoice

# ... (keep get, list, send, void, and pdf endpoints as they are, 
# but ensure list_invoices uses get_current_user, which it already does) ...





backend/app/routers/payments.py

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





Once you apply these changes, generate and run the Alembic migration:

cd ~/Documents/Projects/rental-manager-backend
source .venv/bin/activate
alembic revision --autogenerate -m "Link invoices to bookings and enable tenant financials"
alembic upgrade head

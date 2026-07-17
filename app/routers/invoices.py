# app/routers/invoices.py
from fastapi import APIRouter

from .invoice.admin import router as admin_router
from .invoice.public import router as public_router
from .invoice.payments import router as payments_router

router = APIRouter(prefix="/invoices", tags=["invoices"])

router.include_router(admin_router)
router.include_router(public_router)
router.include_router(payments_router)

# app/routers/bookings.py
from fastapi import APIRouter

# Import routers from the singular 'booking' folder
from .booking.management import router as management_router
from .booking.lifecycle import router as lifecycle_router
from .booking.invoices import router as invoices_router
from .booking.extensions import router as extensions_router # ✅ NEW for Milestone 2

router = APIRouter(prefix="/bookings", tags=["bookings"])

router.include_router(management_router)
router.include_router(lifecycle_router)
router.include_router(invoices_router)
router.include_router(extensions_router)

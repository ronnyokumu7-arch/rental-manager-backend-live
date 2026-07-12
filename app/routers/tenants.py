# app/routers/tenants.py
from fastapi import APIRouter
from .tenants.core import router as core_router
from .tenants.lifecycle import router as lifecycle_router
from .tenants.recovery import router as recovery_router
from .tenants.payment_gateways import router as gateway_router

router = APIRouter(prefix="/tenants", tags=["tenants"])

router.include_router(core_router)
router.include_router(lifecycle_router)
router.include_router(recovery_router)
router.include_router(gateway_router)

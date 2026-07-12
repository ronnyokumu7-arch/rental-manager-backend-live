# app/routers/users.py
from fastapi import APIRouter
from .users.management import router as management_router
from .users.lifecycle import router as lifecycle_router
from .users.recovery import router as recovery_router

router = APIRouter(prefix="/users", tags=["users"])

router.include_router(management_router)
router.include_router(lifecycle_router)
router.include_router(recovery_router)

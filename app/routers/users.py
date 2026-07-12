# app/routers/users.py
from fastapi import APIRouter
from .user.management import router as management_router
from .user.lifecycle import router as lifecycle_router
from .user.recovery import router as recovery_router

router = APIRouter(prefix="/users", tags=["users"])

router.include_router(management_router)
router.include_router(lifecycle_router)
router.include_router(recovery_router)

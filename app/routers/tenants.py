# app/routers/tenants.py
import sys
import traceback

print("=" * 60, flush=True)
print("DEBUG: Starting tenants.py router initialization", flush=True)
print("=" * 60, flush=True)

try:
    print("DEBUG: Importing core router...", flush=True)
    from .tenants.core import router as core_router
    print("✓ core router imported", flush=True)
except Exception as e:
    print(f"✗ FAILED to import core router: {e}", flush=True)
    traceback.print_exc()
    raise

try:
    print("DEBUG: Importing lifecycle router...", flush=True)
    from .tenants.lifecycle import router as lifecycle_router
    print("✓ lifecycle router imported", flush=True)
except Exception as e:
    print(f"✗ FAILED to import lifecycle router: {e}", flush=True)
    traceback.print_exc()
    raise

try:
    print("DEBUG: Importing recovery router...", flush=True)
    from .tenants.recovery import router as recovery_router
    print("✓ recovery router imported", flush=True)
except Exception as e:
    print(f"✗ FAILED to import recovery router: {e}", flush=True)
    traceback.print_exc()
    raise

try:
    print("DEBUG: Importing payment_gateways router...", flush=True)
    from .tenants.payment_gateways import router as gateway_router
    print("✓ payment_gateways router imported", flush=True)
except Exception as e:
    print(f"✗ FAILED to import payment_gateways router: {e}", flush=True)
    traceback.print_exc()
    raise

print("DEBUG: Creating main router...", flush=True)
from fastapi import APIRouter
router = APIRouter(prefix="/tenants", tags=["tenants"])

print("DEBUG: Including sub-routers...", flush=True)
router.include_router(core_router)
router.include_router(lifecycle_router)
router.include_router(recovery_router)
router.include_router(gateway_router)

print("=" * 60, flush=True)
print("✓ SUCCESS: All routers loaded", flush=True)
print("=" * 60, flush=True)

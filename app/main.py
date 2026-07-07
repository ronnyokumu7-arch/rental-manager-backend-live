import os
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.exceptions import http_exception_handler
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routers import (
    activity_logs, admin, auth, bookings, clients, contracts,
    invoices, payments, reports, role_templates, subscriptions,
    tasks, tenant_policies, tenant_profile, tenants, users, vehicles,
)
from app.scripts.seed_superadmin import update_password

# ---------------------------------------------------------------------------
# 1. Modern Lifespan Manager (Handles Startup & Shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🌱 Running seed initialization...")
    try:
        update_password()
        print("✅ Seed initialization completed.")
    except Exception as e:
        print(f"⚠️ Warning: Seed initialization encountered an error: {e}")
    
    print("⏰ Starting background scheduler...")
    start_scheduler()
    yield
    print("🛑 Stopping background scheduler...")
    stop_scheduler()

# ---------------------------------------------------------------------------
# 2. Initialize FastAPI App
# ---------------------------------------------------------------------------
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# 3. Bulletproof CORS Configuration
# ---------------------------------------------------------------------------
cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    try:
        # Handle both JSON array strings (e.g., '["url1", "url2"]') and comma-separated strings
        if cors_origins_env.strip().startswith("["):
            origins = json.loads(cors_origins_env)
        else:
            origins = [origin.strip() for origin in cors_origins_env.split(",")]
    except Exception:
        # Fallback if parsing fails
        origins = [
            "http://localhost:3000",
            "http://localhost:3002",
            "http://localhost:5173",
            "https://rental-manager-frontend.vercel.app",
        ]
else:
    origins = settings.cors_origins

print(f"🌍 CORS Origins configured: {origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 4. Mount Static Directories
# ---------------------------------------------------------------------------
if os.path.exists("./uploads"):
    app.mount("/uploads", StaticFiles(directory="./uploads"), name="uploads")
if os.path.exists("./storage/contracts"):
    app.mount("/contracts", StaticFiles(directory="./storage/contracts"), name="contracts")

# ---------------------------------------------------------------------------
# 5. Global Exception Handler & Health Check
# ---------------------------------------------------------------------------
app.add_exception_handler(HTTPException, http_exception_handler)

@app.get("/health", tags=["system"])
def health_check():
    return {
        "status": "ok",
        "environment": settings.environment,
    }

@app.get("/")
def root():
    return {
        "message": "Rental Manager API is running",
        "docs": "/docs",
        "health": "/health"
    }

# ---------------------------------------------------------------------------
# 6. Include All Routers
# ---------------------------------------------------------------------------
routers = [
    auth, tenants, users, clients, vehicles,
    bookings, subscriptions, invoices, payments,
    tenant_profile, tenant_policies, role_templates, contracts,
    admin, reports, activity_logs, tasks # ✅ tasks router included
]

for router in routers:
    app.include_router(router.router, prefix="/api/v1")

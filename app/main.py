from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from app.core.config import get_settings
from app.core.exceptions import http_exception_handler
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routers import (
    admin, auth, bookings, clients, contracts,
    invoices, payments, reports, subscriptions,
    tenant_policies, tenant_profile, tenants,
    users, vehicles, activity_logs,  # ✅ ADDED activity_logs
)
from app.scripts.seed_superadmin import update_password

# 1. Modern Lifespan Manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Running seed initialization...")
    try:
        update_password()
        print("Seed initialization completed.")
    except Exception as e:
        print(f"Warning: Seed initialization encountered an error: {e}")
    start_scheduler()
    yield
    stop_scheduler()

settings = get_settings()

# 2. Initialize FastAPI App
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# 3. CORS Configuration
import json
cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    try:
        origins = json.loads(cors_origins_env)
    except:
        origins = [
            "http://localhost:3000",
            "http://localhost:3002",
            "http://localhost:5173",
            "https://rental-manager-frontend.vercel.app",
        ]
else:
    origins = settings.cors_origins

print(f" CORS Origins configured: {origins}")

# 4. Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 5. Mount directories
if os.path.exists("./uploads"):
    app.mount("/uploads", StaticFiles(directory="./uploads"), name="uploads")
if os.path.exists("./storage/contracts"):
    app.mount("/contracts", StaticFiles(directory="./storage/contracts"), name="contracts")

# 6. Global Exception Handler
app.add_exception_handler(HTTPException, http_exception_handler)

# 7. Health Check
@app.get("/health", tags=["system"])
def health_check():
    return {
        "status": "ok",
        "environment": settings.environment,
    }

# 8. Include all routers
routers = [
    auth, tenants, users, clients, vehicles,
    bookings, subscriptions, invoices, payments,
    tenant_profile, tenant_policies, contracts,
    admin, reports, activity_logs  # ✅ ADDED activity_logs
]

for router in routers:
    app.include_router(router.router, prefix="/api/v1")

# Root endpoint
@app.get("/")
def root():
    return {
        "message": "Rental Manager API is running",
        "docs": "/docs",
        "health": "/health"
    }

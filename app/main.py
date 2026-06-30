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
    invoices, payments, quotations, reports, subscriptions,
    tenant_policies, tenant_profile, tenants,
    users, vehicles,
)
from app.scripts.seed_superadmin import update_password

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    print("Running seed initialization...")
    try:
        update_password()
        print("Seed initialization completed.")
    except Exception as e:
        print(f"Warning: Seed initialization encountered an error: {e}")
    
    start_scheduler()
    yield
    # Shutdown logic
    stop_scheduler()

settings = get_settings()

# CORS Configuration
origins = [
    "http://localhost:3000",  # Your local Next.js dev server
    "http://localhost:3001",  # Just in case
    "https://rental-manager-backend-071n.onrender.com",  # Your actual production backend URL
    "https://your-frontend-domain.com",  # Your actual production frontend URL (add this later)
]

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the uploads directory for serving files
if os.path.exists("./uploads"):
    app.mount("/uploads", StaticFiles(directory="./uploads"), name="uploads")

# Global Exception Handler
app.add_exception_handler(HTTPException, http_exception_handler)

# Health Check
@app.get("/health", tags=["system"])
def health_check():
    return {
        "status": "ok",
        "environment": settings.environment,
    }

# Include all routers ONCE
routers = [
    auth, tenants, users, clients, vehicles,
    bookings, subscriptions, invoices, payments,
    tenant_profile, tenant_policies, contracts,
    admin, reports, quotations  # ✅ Quotations included here ONLY
]

for router in routers:
    app.include_router(router.router, prefix="/api/v1")

# ✅ REMOVED: Duplicate app.include_router(quotations.router, prefix="/api/v1")

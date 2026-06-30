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

settings = get_settings()

# 1. Modern Lifespan Manager (replaces @app.on_event)
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

# 2. Initialize FastAPI App (SINGLE INITIALIZATION)
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# 3. CORS Configuration
# ⚠️ NOTE: These must be your FRONTEND URLs, not the backend URL.
origins = [
    "http://localhost:3000",       # Your local Next.js dev server
    "http://localhost:3001",       # Just in case
    "https://your-frontend-domain.com", # TODO: Add your actual deployed frontend URL here (e.g., Vercel URL)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Mount the uploads directory for serving files
if os.path.exists("./uploads"):
    app.mount("/uploads", StaticFiles(directory="./uploads"), name="uploads")

# 5. Global Exception Handler
app.add_exception_handler(HTTPException, http_exception_handler)

# 6. Health Check
@app.get("/health", tags=["system"])
def health_check():
    return {
        "status": "ok",
        "environment": settings.environment,
    }

# 7. Include Routers
routers = [
    auth, tenants, users, clients, vehicles,
    bookings, subscriptions, invoices, payments,
    tenant_profile, tenant_policies, contracts,
    admin, reports, quotations # ✅ Quotations included here
]

for router in routers:
    app.include_router(router.router, prefix="/api/v1")

# ✅ REMOVED: Duplicate app.include_router(quotations.router, prefix="/api/v1")

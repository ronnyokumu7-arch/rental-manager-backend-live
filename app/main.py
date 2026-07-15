import os
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.exceptions import http_exception_handler
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.scripts.seed_superadmin import update_password
from app.endpoints import health

from app.routers import (
    activity_logs,
    admin,
    auth,
    bookings,
    clients,
    contracts,
    invoices,
    payments,
    reports,
    role_templates,
    subscriptions,
    system,
    user_preferences,
    tasks,
    tenant_policies,
    tenant_profile,
    tenants,
    users,
    vehicles,
    user_preferences,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        update_password()
    except Exception as e:
        print(f"Seed initialization warning: {e}")

    start_scheduler()
    yield
    stop_scheduler()

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
)

cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    try:
        if cors_origins_env.strip().startswith("["):
            origins = json.loads(cors_origins_env)
        else:
            origins = [origin.strip() for origin in cors_origins_env.split(",")]
    except Exception:
        origins = [
            "http://localhost:3000",
            "http://localhost:3002",
            "http://localhost:5173",
            "https://rental-manager-frontend.vercel.app",
        ]
else:
    origins = settings.cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.exists("./uploads"):
    app.mount("/uploads", StaticFiles(directory="./uploads"), name="uploads")

if os.path.exists("./storage/contracts"):
    app.mount("/contracts", StaticFiles(directory="./storage/contracts"), name="contracts")

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

routers = [
    auth,
    tenants,
    users,
    clients,
    vehicles,
    bookings,
    subscriptions,
    invoices,
    payments,
    tenant_profile,
    tenant_policies,
    role_templates,
    contracts,
    admin,
    reports,
    activity_logs,
    tasks,
    system,
]

for router in routers:
    app.include_router(router.router, prefix="/api/v1")

app.include_router(health.router, prefix="/api/v1")

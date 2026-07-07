"""
Seed default role templates for common job titles.
Run this after deploying to populate the permissions matrix.
"""
from sqlalchemy.orm import Session
from app.db.database import engine
from app.models.role_template import RoleTemplate
from app.core.permissions import ALL_PERMISSION_KEYS

# Default role templates with sensible permission sets
DEFAULT_ROLE_TEMPLATES = {
    "Director": {
        "description": "Top-level executive with full agency access",
        "permissions": ALL_PERMISSION_KEYS,  # Full access
    },
    "Manager": {
        "description": "Operational manager with broad access",
        "permissions": [
            "view_dashboard",
            "view_clients", "manage_clients",
            "view_vehicles", "manage_vehicles",
            "view_bookings", "manage_bookings",
            "view_contracts", "manage_contracts",
            "view_financials", "record_payments",
            "view_team", "manage_team",
            "view_reports",
        ],
    },
    "HR": {
        "description": "Human resources administrator",
        "permissions": [
            "view_dashboard",
            "view_team", "manage_team",
            "view_clients",
            "view_bookings",
            "view_financials",
        ],
    },
    "Accountant": {
        "description": "Financial officer",
        "permissions": [
            "view_dashboard",
            "view_clients",
            "view_bookings",
            "view_financials", "record_payments",
            "view_reports",
            "view_contracts",
        ],
    },
    "Cashier": {
        "description": "Payment processing staff",
        "permissions": [
            "view_dashboard",
            "view_clients",
            "view_bookings",
            "record_payments",
        ],
    },
    "Credit Control": {
        "description": "Collections and accounts receivable",
        "permissions": [
            "view_dashboard",
            "view_clients",
            "view_financials",
            "view_reports",
        ],
    },
    "Fleet Manager": {
        "description": "Vehicle operations manager",
        "permissions": [
            "view_dashboard",
            "view_vehicles", "manage_vehicles", "manage_maintenance",
            "view_bookings", "manage_bookings",
            "view_clients",
        ],
    },
    "Driver": {
        "description": "Vehicle operator - minimal access",
        "permissions": [
            "view_dashboard",
            "view_bookings",  # Can only see assigned bookings
        ],
    },
    "Dispatcher": {
        "description": "Booking coordinator",
        "permissions": [
            "view_dashboard",
            "view_clients",
            "view_bookings", "manage_bookings",
            "view_vehicles",
            "view_contracts",
        ],
    },
    "Call Center": {
        "description": "Customer service representative",
        "permissions": [
            "view_dashboard",
            "view_clients",
            "view_bookings", "manage_bookings",
            "view_vehicles",
        ],
    },
    "Sales Rep": {
        "description": "Sales representative",
        "permissions": [
            "view_dashboard",
            "view_clients", "manage_clients",
            "view_bookings", "manage_bookings",
            "view_vehicles",
            "view_contracts", "manage_contracts",
        ],
    },
    "Booking Agent": {
        "description": "Reservation specialist",
        "permissions": [
            "view_dashboard",
            "view_clients",
            "view_bookings", "manage_bookings",
            "view_vehicles",
        ],
    },
    "Customer Care": {
        "description": "Customer support",
        "permissions": [
            "view_dashboard",
            "view_clients",
            "view_bookings",
            "view_contracts",
        ],
    },
    "Contracts Officer": {
        "description": "Contract administrator",
        "permissions": [
            "view_dashboard",
            "view_clients",
            "view_bookings",
            "view_contracts", "manage_contracts",
        ],
    },
    "Marketing Lead": {
        "description": "Marketing manager",
        "permissions": [
            "view_dashboard",
            "view_clients",
            "view_bookings",
            "view_reports",
        ],
    },
    "Partnerships Manager": {
        "description": "Business development",
        "permissions": [
            "view_dashboard",
            "view_clients", "manage_clients",
            "view_bookings",
            "view_reports",
        ],
    },
}

def seed_role_templates(tenant_id: int, db: Session):
    """Create default role templates for a tenant."""
    print(f"Seeding role templates for tenant {tenant_id}...")
    
    created_count = 0
    for job_title, template_data in DEFAULT_ROLE_TEMPLATES.items():
        # Check if template already exists
        existing = db.query(RoleTemplate).filter(
            RoleTemplate.tenant_id == tenant_id,
            RoleTemplate.job_title == job_title
        ).first()
        
        if not existing:
            template = RoleTemplate(
                tenant_id=tenant_id,
                job_title=job_title,
                permissions=template_data["permissions"],
            )
            db.add(template)
            created_count += 1
            print(f"  ✓ Created template: {job_title}")
        else:
            print(f"  - Skipped (exists): {job_title}")
    
    db.commit()
    print(f"✅ Seeded {created_count} role templates for tenant {tenant_id}")

if __name__ == "__main__":
    # This is for manual testing - replace with actual tenant ID
    from app.models.tenants import Tenant
    
    with Session(engine) as session:
        # Get the first tenant (for testing)
        tenant = session.query(Tenant).first()
        if tenant:
            seed_role_templates(tenant.id, session)
        else:
            print("❌ No tenants found. Create a tenant first.")

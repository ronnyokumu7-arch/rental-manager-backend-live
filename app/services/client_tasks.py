from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.clients import Client, ClientStatus
from app.models.task import TaskPriority
from app.services.task_core import TaskCoreService

class ClientTaskService:
    """Handles all task generation logic specific to the Client lifecycle."""

    @staticmethod
    def check_compliance_on_create(db: Session, client: Client, tenant_id: int):
        """Triggered when a new client is added. Checks for pending verification and missing docs."""
        
        # 1. Verification Task (If client is in 'pending' status)
        if client.status == ClientStatus.pending:
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="HR",
                title=f"Verify New Client: {client.full_name}",
                description=f"New client registered. Review submitted details and approve or reject the account.",
                category="hr", priority=TaskPriority.medium,
                due_date=datetime.now() + timedelta(hours=24),
                target_type="client", target_id=client.id
            )

        # 2. Missing Documents Check
        missing_docs = []
        if not client.id_number: missing_docs.append("National ID Number")
        if not client.dl_number: missing_docs.append("Driver's License Number")
        if not client.id_image_front: missing_docs.append("ID Photo")
        if not client.dl_image_front: missing_docs.append("DL Photo")

        if missing_docs:
            missing_list = ", ".join(missing_docs)
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="HR",
                title=f"Request Missing Docs for {client.full_name}",
                description=f"Client profile is incomplete. Please request the following from the client: {missing_list}.",
                category="compliance", priority=TaskPriority.high,
                due_date=datetime.now() + timedelta(hours=12),
                target_type="client", target_id=client.id
            )

    @staticmethod
    def check_dl_expiry(db: Session, client: Client, tenant_id: int):
        """
        Triggered when a client is updated or during daily checks.
        Handles both EXPIRED (fully auto) and NEAR EXPIRY (<7 days).
        """
        if not client.dl_expiry:
            return # No expiry date set, skip check

        today = datetime.now().date()
        expiry_date = client.dl_expiry.date() if hasattr(client.dl_expiry, 'date') else client.dl_expiry
        days_left = (expiry_date - today).days

        # Scenario A: DL is EXPIRED (Fully Auto Action)
        if days_left < 0:
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="HR",
                title=f"URGENT: DL Expired for {client.full_name}",
                description=f"Client's Driver's License expired {abs(days_left)} days ago. Suspend client from making new bookings until renewed.",
                category="compliance", priority=TaskPriority.urgent,
                due_date=datetime.now(), # Due immediately
                target_type="client", target_id=client.id
            )

        # Scenario B: DL is NEAR EXPIRY (< 7 days)
        elif 0 <= days_left < 7:
            TaskCoreService.smart_create_task(
                db=db, tenant_id=tenant_id, target_role="HR",
                title=f"DL Expiring Soon: {client.full_name}",
                description=f"Client's Driver's License expires in {days_left} days ({expiry_date}). Contact client to get a copy of the renewed license.",
                category="compliance", priority=TaskPriority.high,
                due_date=datetime.now() + timedelta(days=2),
                target_type="client", target_id=client.id
            )

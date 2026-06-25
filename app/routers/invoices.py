from fastapi import APIRouter

router = APIRouter(prefix="/invoices", tags=["invoices"])

@router.get("/")
def list_invoices_placeholder():
    return {"message": "Invoice routes coming soon in Phase 3"}

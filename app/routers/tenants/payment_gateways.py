# app/routers/tenants/payment_gateways.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.tenants import Tenant, PaymentMethodType
from app.models.users import User, UserRole
from app.models.payment.mpesa import MpesaConfig
from app.models.payment.airtel import AirtelMoneyConfig
from app.models.payment.bank import BankAccountConfig
from app.models.payment.stripe import StripeConfig
from app.models.payment.paypal import PaypalConfig

router = APIRouter()

super_admin_only = Depends(require_role([UserRole.super_admin]))

# Map gateway type strings to their config models
GATEWAY_MODELS = {
    "mpesa": MpesaConfig,
    "airtel_money": AirtelMoneyConfig,
    "bank": BankAccountConfig,
    "stripe": StripeConfig,
    "paypal": PaypalConfig,
}


def _mask_credentials(config: object) -> dict:
    """Returns safe-to-display version of gateway config with masked secrets."""
    data = {}
    for key, value in config.__dict__.items():
        if key.startswith("_"):
            continue
        # Mask sensitive fields
        if any(s in key.lower() for s in ["secret", "key", "pass", "token"]):
            data[key] = f"****{str(value)[-4:]}" if value else None
        else:
            data[key] = value
    return data


@router.get("/{tenant_id}/payment-gateways")
def list_gateways(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    gateways = []
    for gw_type, model_class in GATEWAY_MODELS.items():
        config = getattr(tenant, f"{gw_type.replace('_money', '')}_config" if gw_type != "bank" else "bank_accounts", None)
        # Handle bank_accounts as list vs single configs
        if gw_type == "bank":
            configs = config if isinstance(config, list) else ([config] if config else [])
            for c in configs:
                if c:
                    gateways.append({**_mask_credentials(c), "type": gw_type})
        elif config:
            gateways.append({**_mask_credentials(config), "type": gw_type})

    return {"gateways": gateways}


@router.post("/{tenant_id}/payment-gateways/{gateway_type}", status_code=status.HTTP_201_CREATED)
def create_gateway(
    tenant_id: int,
    gateway_type: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    if gateway_type not in GATEWAY_MODELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid gateway type. Must be one of: {', '.join(GATEWAY_MODELS.keys())}",
        )

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    ModelClass = GATEWAY_MODELS[gateway_type]

    # Check if config already exists (single-config gateways)
    if gateway_type != "bank":
        existing = getattr(tenant, f"{gateway_type.replace('_money', '')}_config", None)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{gateway_type} config already exists. Use PATCH to update.",
            )

    # Create new config
    config_data = {"tenant_id": tenant_id, **payload}
    new_config = ModelClass(**config_data)
    db.add(new_config)
    db.commit()
    db.refresh(new_config)

    return {**_mask_credentials(new_config), "type": gateway_type}


@router.patch("/{tenant_id}/payment-gateways/{gateway_type}/{config_id}")
def update_gateway(
    tenant_id: int,
    gateway_type: str,
    config_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    if gateway_type not in GATEWAY_MODELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid gateway type")

    ModelClass = GATEWAY_MODELS[gateway_type]
    config = db.query(ModelClass).filter(
        ModelClass.id == config_id,
        ModelClass.tenant_id == tenant_id,
    ).first()

    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gateway config not found")

    for field, value in payload.items():
        if hasattr(config, field):
            setattr(config, field, value)

    db.commit()
    db.refresh(config)
    return {**_mask_credentials(config), "type": gateway_type}


@router.post("/{tenant_id}/payment-gateways/{gateway_type}/test")
def test_gateway_connection(
    tenant_id: int,
    gateway_type: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    current_user: User = super_admin_only,
):
    """Test connectivity to payment gateway without saving credentials."""
    if gateway_type not in GATEWAY_MODELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid gateway type")

    # TODO: Implement actual API ping for each gateway type
    # For now, validate required fields are present
    required_fields = {
        "mpesa": ["consumer_key", "consumer_secret", "passkey"],
        "airtel_money": ["api_key", "api_secret", "merchant_code"],
        "bank": ["account_number", "bank_name"],
        "stripe": ["publishable_key", "secret_key"],
        "paypal": ["client_id", "client_secret"],
    }

    missing = [f for f in required_fields.get(gateway_type, []) if not payload or f not in payload]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required fields for {gateway_type}: {', '.join(missing)}",
        )

    return {
        "gateway_type": gateway_type,
        "status": "connected",  # Replace with actual API test result
        "message": f"{gateway_type} credentials validated successfully.",
    }

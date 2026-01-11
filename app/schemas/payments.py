"""Payment request/response schemas."""
from datetime import datetime
from typing import Optional
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class AmountSchema(BaseModel):
    """Amount with currency."""
    amount: Decimal = Field(..., gt=0, description="Payment amount")
    currency: str = Field(..., min_length=3, max_length=10, description="Currency code (EUR, USD, etc.)")


class PaymentCreateRequest(BaseModel):
    """Request schema for POST /payments."""
    payment_method: str = Field(..., description="Payment method (BTC_LN)")
    amount: Decimal = Field(..., gt=0, description="Payment amount")
    currency: str = Field(..., min_length=3, max_length=10, description="Currency code")
    external_code: str = Field(..., min_length=1, max_length=64, description="Merchant order ID")
    description: Optional[str] = Field(None, max_length=500, description="Payment description")
    callback_url: Optional[HttpUrl] = Field(None, max_length=2048, description="Client callback URL")
    redirect_url: Optional[HttpUrl] = Field(None, max_length=2048, description="Client redirect URL")
    metadata: Optional[dict] = Field(default_factory=dict, description="Additional metadata")
    idempotency_key: Optional[str] = Field(None, max_length=255, description="Idempotency key")

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, v):
        """Ensure metadata JSON is not too large."""
        import json
        json_str = json.dumps(v)
        if len(json_str) > 8192:  # 8KB limit
            raise ValueError("Metadata too large (max 8KB)")
        return v


class InvoiceSchema(BaseModel):
    """Invoice details."""
    provider: str
    provider_invoice_id: str
    checkout_link: Optional[str] = None
    bolt11: Optional[str] = None
    expires_at: Optional[datetime] = None


class PaymentResponse(BaseModel):
    """Response schema for payment endpoints."""
    payment_id: UUID
    status: str
    monitor_until: datetime
    invoice: InvoiceSchema
    amount: AmountSchema
    metadata: dict
    external_code: str
    created_at: datetime
    finalized_at: Optional[datetime] = None
    status_reason: Optional[str] = None
    # Lightning invoice for QR code display
    lightning_invoice: Optional[str] = Field(None, description="BOLT11 Lightning invoice string for QR code display")


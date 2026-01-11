"""SSE event schemas."""
from datetime import datetime
from typing import Optional
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel


class AmountSchema(BaseModel):
    """Amount with currency."""
    amount: Decimal
    currency: str


class PaymentInfoSchema(BaseModel):
    """Payment information in SSE event."""
    payment_id: UUID
    external_code: str
    status: str
    status_reason: Optional[str] = None
    created_at: datetime
    finalized_at: Optional[datetime] = None
    monitor_until: datetime
    amount: AmountSchema
    payment_method: str


class InvoiceInfoSchema(BaseModel):
    """Invoice information in SSE event."""
    provider: str
    provider_invoice_id: str
    checkout_link: Optional[str] = None
    bolt11: Optional[str] = None
    expires_at: Optional[datetime] = None


class ProviderStatusSchema(BaseModel):
    """Provider status information."""
    btcpay_status: Optional[str] = None
    seen_at: datetime
    source: str  # BTCPAY_WEBHOOK, WORKER_POLL, API_CREATE


class SSEEventData(BaseModel):
    """SSE event data payload."""
    event_id: int
    event: str
    emitted_at: datetime
    payment: PaymentInfoSchema
    invoice: Optional[InvoiceInfoSchema] = None
    provider_status: Optional[ProviderStatusSchema] = None


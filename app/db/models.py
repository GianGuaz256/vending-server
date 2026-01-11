"""SQLAlchemy database models."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Numeric,
    BigInteger,
    Text,
    ForeignKey,
    UniqueConstraint,
    Index,
    JSON,
    ARRAY,
    Sequence,
)
from sqlalchemy.dialects.postgresql import UUID, INET, CIDR
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class Client(Base):
    """Client/terminal device that can authenticate and create payments."""

    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    machine_id = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    allowed_ips = Column(ARRAY(CIDR), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    client_metadata = Column(JSON, nullable=True, default=dict)

    # Relationships
    payment_requests = relationship("PaymentRequest", back_populates="client", cascade="all, delete-orphan")
    auth_events = relationship("ClientAuthEvent", back_populates="client", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Client(id={self.id}, machine_id={self.machine_id})>"


class ClientAuthEvent(Base):
    """Audit log for client authentication events."""

    __tablename__ = "client_auth_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # LOGIN_OK, LOGIN_FAIL, TOKEN_ISSUED, TOKEN_REVOKED
    ip = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    details = Column(JSON, nullable=True, default=dict)

    # Relationships
    client = relationship("Client", back_populates="auth_events")

    def __repr__(self):
        return f"<ClientAuthEvent(id={self.id}, event_type={self.event_type})>"


class PaymentRequest(Base):
    """Logical payment object exposed to clients."""

    __tablename__ = "payment_requests"

    # Status enum values
    STATUS_CREATED = "CREATED"
    STATUS_PENDING = "PENDING"
    STATUS_PAID = "PAID"
    STATUS_TIMED_OUT = "TIMED_OUT"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_FAILED = "FAILED"
    STATUS_CANCELED = "CANCELED"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True)
    external_code = Column(String(64), nullable=False)  # Merchant order ID
    payment_method = Column(String(50), nullable=False)  # BTC_LN, USDT_TRC20, etc.
    amount = Column(Numeric(18, 8), nullable=False)
    currency = Column(String(10), nullable=False)  # EUR, CHF, USD, BTC
    amount_sats = Column(BigInteger, nullable=True)  # Computed sats equivalent
    description = Column(Text, nullable=True)
    callback_url = Column(Text, nullable=True)
    redirect_url = Column(Text, nullable=True)
    payment_metadata = Column(JSON, nullable=False, default=dict)
    idempotency_key = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default=STATUS_CREATED, index=True)
    status_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    monitor_until = Column(DateTime(timezone=True), nullable=False)
    finalized_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    client = relationship("Client", back_populates="payment_requests")
    provider_invoice = relationship("ProviderInvoice", back_populates="payment_request", uselist=False, cascade="all, delete-orphan")
    events = relationship("PaymentEvent", back_populates="payment_request", cascade="all, delete-orphan", order_by="PaymentEvent.seq")

    # Constraints
    __table_args__ = (
        UniqueConstraint("client_id", "idempotency_key", name="uq_client_idempotency"),
        Index("idx_payment_client_created", "client_id", "created_at"),
        Index("idx_payment_status_monitor", "status", "monitor_until"),
    )

    def __repr__(self):
        return f"<PaymentRequest(id={self.id}, status={self.status}, external_code={self.external_code})>"


class ProviderInvoice(Base):
    """Provider-specific invoice linkage (BTCPay now; other providers later)."""

    __tablename__ = "provider_invoices"

    PROVIDER_BTCPAY = "BTCPAY"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_request_id = Column(UUID(as_uuid=True), ForeignKey("payment_requests.id"), nullable=False, unique=True, index=True)
    provider = Column(String(50), nullable=False)  # BTCPAY
    provider_invoice_id = Column(String(255), nullable=False, index=True)
    store_id = Column(String(255), nullable=False)
    checkout_link = Column(Text, nullable=True)
    bolt11 = Column(Text, nullable=True)  # Lightning invoice string
    expires_at = Column(DateTime(timezone=True), nullable=True)
    raw_create_response = Column(JSON, nullable=False)
    raw_last_status = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    payment_request = relationship("PaymentRequest", back_populates="provider_invoice")

    def __repr__(self):
        return f"<ProviderInvoice(id={self.id}, provider={self.provider}, provider_invoice_id={self.provider_invoice_id})>"


class PaymentEvent(Base):
    """Immutable status timeline for payment requests."""

    __tablename__ = "payment_events"

    # Event types
    EVENT_CREATED = "CREATED"
    EVENT_PROVIDER_INVOICE_CREATED = "PROVIDER_INVOICE_CREATED"
    EVENT_WEBHOOK_RECEIVED = "WEBHOOK_RECEIVED"
    EVENT_PAID = "PAID"
    EVENT_TIMED_OUT = "TIMED_OUT"
    EVENT_EXPIRED = "EXPIRED"
    EVENT_FAILED = "FAILED"
    EVENT_CANCELED = "CANCELED"

    # Source types
    SOURCE_API = "API"
    SOURCE_WORKER = "WORKER"
    SOURCE_BTCPAY_WEBHOOK = "BTCPAY_WEBHOOK"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seq = Column(BigInteger, Sequence("payment_events_seq"), nullable=False, unique=True, index=True)  # Monotonic sequence for SSE replay
    payment_request_id = Column(UUID(as_uuid=True), ForeignKey("payment_requests.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    old_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=True)
    source = Column(String(50), nullable=False)  # API, WORKER, BTCPAY_WEBHOOK
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    payload = Column(JSON, nullable=True, default=dict)

    # Relationships
    payment_request = relationship("PaymentRequest", back_populates="events")

    # Indexes for efficient SSE replay
    __table_args__ = (
        Index("idx_payment_events_seq", "seq"),
        Index("idx_payment_events_payment_seq", "payment_request_id", "seq"),
    )

    def __repr__(self):
        return f"<PaymentEvent(seq={self.seq}, event_type={self.event_type}, payment_request_id={self.payment_request_id})>"


"""Server-Sent Events (SSE) endpoints for real-time payment updates."""
import json
import asyncio
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Header
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session
import redis

from app.api.deps import get_current_client
from app.db.session import get_db
from app.db.models import PaymentRequest, PaymentEvent, ProviderInvoice
from app.schemas.events import SSEEventData, PaymentInfoSchema, InvoiceInfoSchema, ProviderStatusSchema, AmountSchema
from app.core.config import settings

router = APIRouter()

# Redis client for pub/sub
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


@router.get("/events/stream")
async def event_stream(
    request: Request,
    client_id: UUID = Depends(get_current_client),
    db: Session = Depends(get_db),
    last_event_id: Optional[int] = Header(None, alias="Last-Event-ID"),
):
    """
    SSE stream for payment events for the authenticated client.
    
    Supports reconnection with Last-Event-ID header for replay.
    """
    async def event_generator():
        # Replay missed events if Last-Event-ID provided
        if last_event_id:
            missed_events = db.query(PaymentEvent).join(PaymentRequest).filter(
                PaymentRequest.client_id == client_id,
                PaymentEvent.seq > last_event_id,
            ).order_by(PaymentEvent.seq).all()
            
            for event in missed_events:
                event_data = _build_sse_event_data(event, db)
                if event_data:
                    yield {
                        "id": str(event.seq),
                        "event": _map_event_type_to_sse(event.event_type),
                        "data": event_data.model_dump_json(),
                    }
        
        # Subscribe to Redis pub/sub for new events
        pubsub = redis_client.pubsub()
        channel = f"client:{client_id}:events"
        pubsub.subscribe(channel)
        
        last_sent_seq = last_event_id or 0
        last_keepalive = datetime.now(timezone.utc)
        
        try:
            while True:
                # Check for disconnection
                if await request.is_disconnected():
                    break
                
                # Check Redis for new messages (non-blocking)
                message = pubsub.get_message(timeout=0.1)
                if message and message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        payment_id = UUID(data["payment_id"])
                        event_seq = data["event_seq"]
                        
                        # Only send if we haven't sent this event yet
                        if event_seq > last_sent_seq:
                            # Query event from DB
                            event = db.query(PaymentEvent).filter(
                                PaymentEvent.seq == event_seq,
                                PaymentEvent.payment_request_id == payment_id,
                            ).first()
                            
                            if event:
                                # Verify ownership
                                payment = event.payment_request
                                if payment.client_id == client_id:
                                    event_data = _build_sse_event_data(event, db)
                                    if event_data:
                                        yield {
                                            "id": str(event.seq),
                                            "event": _map_event_type_to_sse(event.event_type),
                                            "data": event_data.model_dump_json(),
                                        }
                                        last_sent_seq = event_seq
                    except Exception as e:
                        print(f"Error processing SSE message: {e}")
                        continue
                
                # Send keepalive every 15 seconds
                now = datetime.now(timezone.utc)
                if (now - last_keepalive).total_seconds() >= 15:
                    yield {
                        "event": "keepalive",
                        "data": json.dumps({"ts": now.isoformat()}),
                    }
                    last_keepalive = now
                
                # Small sleep to prevent busy loop
                await asyncio.sleep(0.1)
        
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()
    
    return EventSourceResponse(event_generator())




def _build_sse_event_data(event: PaymentEvent, db: Session) -> Optional[SSEEventData]:
    """Build SSE event data from PaymentEvent."""
    payment = event.payment_request
    provider_invoice = payment.provider_invoice
    
    # Build payment info
    payment_info = PaymentInfoSchema(
        payment_id=payment.id,
        external_code=payment.external_code,
        status=payment.status,
        status_reason=payment.status_reason,
        created_at=payment.created_at,
        finalized_at=payment.finalized_at,
        monitor_until=payment.monitor_until,
        amount=AmountSchema(
            amount=payment.amount,
            currency=payment.currency,
        ),
        payment_method=payment.payment_method,
    )
    
    # Build invoice info if available
    invoice_info = None
    if provider_invoice:
        invoice_info = InvoiceInfoSchema(
            provider=provider_invoice.provider,
            provider_invoice_id=provider_invoice.provider_invoice_id,
            checkout_link=provider_invoice.checkout_link,
            bolt11=provider_invoice.bolt11,
            expires_at=provider_invoice.expires_at,
        )
    
    # Build provider status if available
    provider_status = None
    if provider_invoice and provider_invoice.raw_last_status:
        status_data = provider_invoice.raw_last_status
        provider_status = ProviderStatusSchema(
            btcpay_status=status_data.get("status"),
            seen_at=provider_invoice.updated_at or datetime.now(timezone.utc),
            source=event.source,
        )
    
    return SSEEventData(
        event_id=event.seq,
        event=_map_event_type_to_sse(event.event_type),
        emitted_at=event.created_at,
        payment=payment_info,
        invoice=invoice_info,
        provider_status=provider_status,
    )


def _map_event_type_to_sse(event_type: str) -> str:
    """Map internal event type to SSE event name."""
    mapping = {
        PaymentEvent.EVENT_CREATED: "payment.created",
        PaymentEvent.EVENT_PROVIDER_INVOICE_CREATED: "payment.invoice_created",
        PaymentEvent.EVENT_WEBHOOK_RECEIVED: "payment.status_changed",
        PaymentEvent.EVENT_PAID: "payment.paid",
        PaymentEvent.EVENT_TIMED_OUT: "payment.timed_out",
        PaymentEvent.EVENT_EXPIRED: "payment.expired",
        PaymentEvent.EVENT_FAILED: "payment.failed",
        PaymentEvent.EVENT_CANCELED: "payment.canceled",
    }
    return mapping.get(event_type, "payment.status_changed")


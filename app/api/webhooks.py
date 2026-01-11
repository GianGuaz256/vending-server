"""Webhook endpoints for external services."""
from fastapi import APIRouter, Request, HTTPException, status, Header, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.core.security import verify_hmac_signature
from app.db.session import get_db
from app.db.models import (
    PaymentRequest,
    ProviderInvoice,
    PaymentEvent,
)
from app.services.notifications import publish_payment_event, send_callback

router = APIRouter()


@router.post("/webhooks/btcpay")
async def btcpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_btcpay_sig: Optional[str] = Header(None, alias="BTCPay-Sig"),
):
    """
    Handle BTCPay Server webhook events.
    
    BTCPay sends webhooks with signature in BTCPay-Sig header.
    Format: sha256=<hex_signature>
    """
    # Get raw body for signature verification
    body = await request.body()
    
    # Verify signature
    if not x_btcpay_sig:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing signature header",
        )
    
    # Extract signature (format: sha256=<hex>)
    if not x_btcpay_sig.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature format",
        )
    
    signature = x_btcpay_sig[7:]  # Remove "sha256=" prefix
    
    # Verify HMAC signature
    if not verify_hmac_signature(body, signature, settings.btcpay_webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )
    
    # Parse webhook payload
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {str(e)}",
        )
    
    # Extract invoice ID and event type
    invoice_id = payload.get("invoiceId") or payload.get("invoice", {}).get("id")
    event_type = payload.get("type") or payload.get("eventType")
    
    if not invoice_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing invoice ID",
        )
    
    # Find provider invoice
    provider_invoice = db.query(ProviderInvoice).filter(
        ProviderInvoice.provider_invoice_id == invoice_id,
    ).first()
    
    if not provider_invoice:
        # Invoice not found - might be for another store or test webhook
        return {"status": "ignored", "reason": "invoice_not_found"}
    
    payment = provider_invoice.payment_request
    
    # Check if already finalized (idempotency)
    if payment.finalized_at:
        return {"status": "ignored", "reason": "already_finalized"}
    
    # Handle different event types
    now = datetime.now(timezone.utc)
    
    # BTCPay event types: InvoiceSettled, InvoiceExpired, InvoiceInvalid, etc.
    if event_type in ("InvoiceSettled", "invoice.settled"):
        # Payment received
        if payment.status != PaymentRequest.STATUS_PAID:
            old_status = payment.status
            payment.status = PaymentRequest.STATUS_PAID
            payment.finalized_at = now
            
            # Update provider invoice status
            invoice_data = payload.get("invoice") or payload.get("data", {})
            provider_invoice.raw_last_status = invoice_data
            
            # Create event
            event = PaymentEvent(
                payment_request_id=payment.id,
                event_type=PaymentEvent.EVENT_PAID,
                old_status=old_status,
                new_status=PaymentRequest.STATUS_PAID,
                source=PaymentEvent.SOURCE_BTCPAY_WEBHOOK,
                payload=payload,
            )
            db.add(event)
            db.commit()
            
            # Publish notification
            publish_payment_event(str(payment.client_id), str(payment.id), event.seq)
            
            # Send callback if configured
            if payment.callback_url:
                import asyncio
                asyncio.run(send_callback(
                    payment.callback_url,
                    payment.id,
                    PaymentRequest.STATUS_PAID,
                    now,
                ))
            
            return {"status": "processed", "payment_id": str(payment.id)}
    
    elif event_type in ("InvoiceExpired", "invoice.expired"):
        # Invoice expired (but we still monitor for 2 minutes)
        # Only mark as expired if it's past our monitor window
        if now >= payment.monitor_until:
            old_status = payment.status
            payment.status = PaymentRequest.STATUS_EXPIRED
            payment.status_reason = "PROVIDER_EXPIRED"
            payment.finalized_at = now
            
            # Create event
            event = PaymentEvent(
                payment_request_id=payment.id,
                event_type=PaymentEvent.EVENT_EXPIRED,
                old_status=old_status,
                new_status=PaymentRequest.STATUS_EXPIRED,
                source=PaymentEvent.SOURCE_BTCPAY_WEBHOOK,
                payload=payload,
            )
            db.add(event)
            db.commit()
            
            # Publish notification
            publish_payment_event(str(payment.client_id), str(payment.id), event.seq)
            
            return {"status": "processed", "payment_id": str(payment.id)}
        else:
            # Still within monitor window, just log the event
            event = PaymentEvent(
                payment_request_id=payment.id,
                event_type=PaymentEvent.EVENT_WEBHOOK_RECEIVED,
                old_status=payment.status,
                new_status=payment.status,
                source=PaymentEvent.SOURCE_BTCPAY_WEBHOOK,
                payload=payload,
            )
            db.add(event)
            db.commit()
            return {"status": "logged", "payment_id": str(payment.id)}
    
    elif event_type in ("InvoiceInvalid", "invoice.invalid", "InvoiceFailed", "invoice.failed"):
        # Invoice failed
        old_status = payment.status
        payment.status = PaymentRequest.STATUS_FAILED
        payment.status_reason = f"PROVIDER_ERROR: {event_type}"
        payment.finalized_at = now
        
        # Create event
        event = PaymentEvent(
            payment_request_id=payment.id,
            event_type=PaymentEvent.EVENT_FAILED,
            old_status=old_status,
            new_status=PaymentRequest.STATUS_FAILED,
            source=PaymentEvent.SOURCE_BTCPAY_WEBHOOK,
            payload=payload,
        )
        db.add(event)
        db.commit()
        
        # Publish notification
        publish_payment_event(str(payment.client_id), str(payment.id), event.seq)
        
        return {"status": "processed", "payment_id": str(payment.id)}
    
    else:
        # Unknown event type - just log it
        event = PaymentEvent(
            payment_request_id=payment.id,
            event_type=PaymentEvent.EVENT_WEBHOOK_RECEIVED,
            old_status=payment.status,
            new_status=payment.status,
            source=PaymentEvent.SOURCE_BTCPAY_WEBHOOK,
            payload=payload,
        )
        db.add(event)
        db.commit()
        return {"status": "logged", "payment_id": str(payment.id), "event_type": event_type}


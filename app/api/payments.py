"""Payment endpoints."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import limiter, get_client_rate_limit_key
from app.db.session import get_db
from app.db.models import (
    PaymentRequest,
    ProviderInvoice,
    PaymentEvent,
    Client,
)
from app.api.deps import get_current_client
from app.schemas.payments import PaymentCreateRequest, PaymentResponse, InvoiceSchema, AmountSchema
from app.services.btcpay import get_btcpay_client
from app.services.notifications import publish_payment_event
from app.worker.tasks import monitor_payment

router = APIRouter()


@router.post("/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def create_payment(
    request: PaymentCreateRequest,
    client_id: UUID = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    """Create a new payment request."""
    # Validate payment method
    if request.payment_method != "BTC_LN":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported payment method: {request.payment_method}",
        )
    
    # Check idempotency
    if request.idempotency_key:
        existing = db.query(PaymentRequest).filter(
            PaymentRequest.client_id == client_id,
            PaymentRequest.idempotency_key == request.idempotency_key,
        ).first()
        
        if existing:
            # Return existing payment
            return _payment_to_response(existing, db)
    
    # Calculate monitor_until timestamp (2 minutes from now)
    monitor_until = datetime.now(timezone.utc) + timedelta(seconds=settings.payment_monitor_seconds)
    
    # Create payment request
    payment = PaymentRequest(
        client_id=client_id,
        external_code=request.external_code,
        payment_method=request.payment_method,
        amount=request.amount,
        currency=request.currency,
        description=request.description,
        callback_url=str(request.callback_url) if request.callback_url else None,
        redirect_url=str(request.redirect_url) if request.redirect_url else None,
        payment_metadata=request.metadata or {},
        idempotency_key=request.idempotency_key,
        status=PaymentRequest.STATUS_CREATED,
        monitor_until=monitor_until,
    )
    db.add(payment)
    db.flush()  # Get payment.id
    
    # Log CREATED event
    _create_payment_event(
        db,
        payment.id,
        PaymentEvent.EVENT_CREATED,
        None,
        PaymentRequest.STATUS_CREATED,
        PaymentEvent.SOURCE_API,
    )
    
    # Create BTCPay invoice
    try:
        btcpay = get_btcpay_client()
        btcpay_response = btcpay.create_invoice(
            amount=float(request.amount),
            currency=request.currency,
            metadata={
                "payment_id": str(payment.id),
                "external_code": request.external_code,
                **request.metadata,
            },
            redirect_url=str(request.redirect_url) if request.redirect_url else None,
        )
        
        invoice_id = btcpay_response.get("id")
        if not invoice_id:
            raise ValueError("BTCPay response missing invoice ID")
        
        checkout_link = btcpay_response.get("checkoutLink")
        
        # Extract BOLT11 - try multiple approaches
        bolt11 = None
        
        # Method 1: Check availablePaymentMethods in create response
        available_methods = btcpay_response.get("availablePaymentMethods", [])
        if available_methods:
            for method in available_methods:
                method_name = method.get("paymentMethod") or method.get("paymentMethodId")
                if method_name == "BTC-LightningNetwork":
                    # BOLT11 is in paymentLink field (BTCPay Greenfield API)
                    payment_link = method.get("paymentLink")
                    if payment_link:
                        # If it's a string starting with lnbc, it's the BOLT11
                        if isinstance(payment_link, str) and payment_link.startswith("lnbc"):
                            bolt11 = payment_link
                            break
                        # If it's a dict, check nested fields
                        elif isinstance(payment_link, dict):
                            bolt11 = payment_link.get("paymentLink") or payment_link.get("destination")
                            if bolt11 and isinstance(bolt11, str) and bolt11.startswith("lnbc"):
                                break
                    # Also check destination field directly
                    destination = method.get("destination")
                    if destination and isinstance(destination, str) and destination.startswith("lnbc"):
                        bolt11 = destination
                        break
        
        # Method 2: Always fetch invoice details (BTCPay often doesn't include payment methods in create response)
        # The create response might not have availablePaymentMethods populated immediately
        import time
        
        if not bolt11:
            # Fetch invoice details - BTCPay generates payment methods asynchronously
            time.sleep(0.5)  # Small delay for BTCPay to generate Lightning invoice
            bolt11 = btcpay.get_bolt11(invoice_id)
        
        # If still not found, try one more time after longer delay
        if not bolt11:
            time.sleep(1.0)
            bolt11 = btcpay.get_bolt11(invoice_id)
        
        if not checkout_link:
            checkout_link = btcpay.get_checkout_link(invoice_id)
        
        expires_at = btcpay.get_expires_at(invoice_id)
        
        # Create provider invoice record
        provider_invoice = ProviderInvoice(
            payment_request_id=payment.id,
            provider=ProviderInvoice.PROVIDER_BTCPAY,
            provider_invoice_id=invoice_id,
            store_id=settings.btcpay_store_id,
            checkout_link=checkout_link,
            bolt11=bolt11,
            expires_at=expires_at,
            raw_create_response=btcpay_response,
        )
        db.add(provider_invoice)
        
        # Update payment status to PENDING
        payment.status = PaymentRequest.STATUS_PENDING
        
        # Log PROVIDER_INVOICE_CREATED event
        _create_payment_event(
            db,
            payment.id,
            PaymentEvent.EVENT_PROVIDER_INVOICE_CREATED,
            PaymentRequest.STATUS_CREATED,
            PaymentRequest.STATUS_PENDING,
            PaymentEvent.SOURCE_API,
            payload={"provider_invoice_id": invoice_id},
        )
        
        db.commit()
        
        # Publish notification for SSE
        publish_payment_event(str(client_id), str(payment.id), payment.events[-1].seq)
        
        # Enqueue monitoring task
        monitor_payment.delay(str(payment.id))
        
        return _payment_to_response(payment, db)
        
    except Exception as e:
        # Rollback first to discard the payment record
        db.rollback()
        
        # Now mark payment as failed and commit it with the event
        # We need to re-query since the rollback cleared the session
        try:
            payment.status = PaymentRequest.STATUS_FAILED
            payment.status_reason = f"BTCPay error: {str(e)}"
            db.add(payment)  # Re-add to session after rollback
            db.flush()  # Ensure payment exists before creating event
            
            _create_payment_event(
                db,
                payment.id,
                PaymentEvent.EVENT_FAILED,
                PaymentRequest.STATUS_CREATED,
                PaymentRequest.STATUS_FAILED,
                PaymentEvent.SOURCE_API,
                payload={"error": str(e)},
            )
            db.commit()
        except Exception as commit_error:
            # If we can't even save the failed state, just rollback
            db.rollback()
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to save payment failure state: {commit_error}")
        
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create invoice: {str(e)}",
        )


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: UUID,
    client_id: UUID = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    """Get payment status by ID."""
    payment = db.query(PaymentRequest).filter(
        PaymentRequest.id == payment_id,
        PaymentRequest.client_id == client_id,
    ).first()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )
    
    return _payment_to_response(payment, db)


def _payment_to_response(payment: PaymentRequest, db: Session) -> PaymentResponse:
    """Convert PaymentRequest model to PaymentResponse schema."""
    provider_invoice = payment.provider_invoice
    
    invoice = None
    if provider_invoice:
        invoice = InvoiceSchema(
            provider=provider_invoice.provider,
            provider_invoice_id=provider_invoice.provider_invoice_id,
            checkout_link=provider_invoice.checkout_link,
            bolt11=provider_invoice.bolt11,
            expires_at=provider_invoice.expires_at,
        )
    else:
        # Return minimal invoice if not yet created
        invoice = InvoiceSchema(
            provider="BTCPAY",
            provider_invoice_id="",
        )
    
    # Extract BOLT11 for easy QR code access
    lightning_invoice = None
    if provider_invoice and provider_invoice.bolt11:
        lightning_invoice = provider_invoice.bolt11
    
    return PaymentResponse(
        payment_id=payment.id,
        status=payment.status,
        monitor_until=payment.monitor_until,
        invoice=invoice,
        amount=AmountSchema(
            amount=payment.amount,
            currency=payment.currency,
        ),
        metadata=payment.payment_metadata,
        external_code=payment.external_code,
        created_at=payment.created_at,
        finalized_at=payment.finalized_at,
        status_reason=payment.status_reason,
        lightning_invoice=lightning_invoice,
    )


def _create_payment_event(
    db: Session,
    payment_id: UUID,
    event_type: str,
    old_status: Optional[str],
    new_status: str,
    source: str,
    payload: Optional[dict] = None,
):
    """Helper to create payment event."""
    event = PaymentEvent(
        payment_request_id=payment_id,
        event_type=event_type,
        old_status=old_status,
        new_status=new_status,
        source=source,
        payload=payload or {},
    )
    db.add(event)
    db.flush()  # Get seq number
    return event


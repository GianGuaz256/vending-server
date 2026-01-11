"""Celery tasks for payment monitoring."""
import time
from datetime import datetime, timezone
from uuid import UUID

from app.worker.celery_app import celery_app
from app.db.session import get_session_local
from app.db.models import (
    PaymentRequest,
    ProviderInvoice,
    PaymentEvent,
)
from app.services.btcpay import BTCPayClient
from app.services.notifications import publish_payment_event, send_callback
from app.core.config import settings


@celery_app.task(name="monitor_payment", bind=True, max_retries=0)
def monitor_payment(self, payment_id: str):
    """
    Monitor payment for 2 minutes from creation.
    
    - Polls BTCPay every 5 seconds as webhook fallback
    - Marks TIMED_OUT if not paid within window
    - Triggers notifications on status change
    """
    SessionLocal = get_session_local()
    db = SessionLocal()
    
    try:
        payment = db.query(PaymentRequest).filter(PaymentRequest.id == UUID(payment_id)).first()
        if not payment:
            print(f"Payment {payment_id} not found")
            return
        
        # If already finalized, skip
        if payment.finalized_at:
            print(f"Payment {payment_id} already finalized")
            return
        
        provider_invoice = payment.provider_invoice
        if not provider_invoice:
            print(f"No provider invoice for payment {payment_id}")
            return
        
        btcpay = BTCPayClient()
        
        try:
            # Loop until monitor_until time
            while datetime.now(timezone.utc) < payment.monitor_until:
                # Refresh payment from DB (webhook may have updated it)
                db.refresh(payment)
                
                # If already finalized by webhook, exit
                if payment.finalized_at:
                    print(f"Payment {payment_id} finalized by webhook")
                    break
                
                # Poll BTCPay status
                try:
                    is_settled = btcpay.is_settled(provider_invoice.provider_invoice_id)
                    
                    if is_settled:
                        # Payment received!
                        _mark_payment_paid(db, payment, provider_invoice, btcpay)
                        break
                    
                    # Update provider status
                    invoice_data = btcpay.get_invoice(provider_invoice.provider_invoice_id)
                    provider_invoice.raw_last_status = invoice_data
                    db.commit()
                    
                except Exception as e:
                    print(f"Error polling BTCPay for {payment_id}: {e}")
                    # Continue monitoring despite poll error
                
                # Sleep before next poll
                time.sleep(settings.payment_poll_interval_seconds)
            
            # Check if we exited loop without payment
            db.refresh(payment)
            if not payment.finalized_at:
                # Timeout reached without payment
                _mark_payment_timed_out(db, payment)
        
        finally:
            btcpay.close()
    
    except Exception as e:
        print(f"Error in monitor_payment for {payment_id}: {e}")
        db.rollback()
        raise
    
    finally:
        db.close()


def _mark_payment_paid(db, payment: PaymentRequest, provider_invoice: ProviderInvoice, btcpay: BTCPayClient):
    """Mark payment as paid and notify."""
    if payment.finalized_at:
        return  # Already finalized
    
    now = datetime.now(timezone.utc)
    
    # Update payment
    payment.status = PaymentRequest.STATUS_PAID
    payment.finalized_at = now
    
    # Update provider invoice status
    invoice_data = btcpay.get_invoice(provider_invoice.provider_invoice_id)
    provider_invoice.raw_last_status = invoice_data
    
    # Create event
    old_status = payment.status
    event = PaymentEvent(
        payment_request_id=payment.id,
        event_type=PaymentEvent.EVENT_PAID,
        old_status=old_status,
        new_status=PaymentRequest.STATUS_PAID,
        source=PaymentEvent.SOURCE_WORKER,
        payload={"btcpay_status": invoice_data.get("status")},
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


def _mark_payment_timed_out(db, payment: PaymentRequest):
    """Mark payment as timed out and notify."""
    if payment.finalized_at:
        return  # Already finalized
    
    now = datetime.now(timezone.utc)
    
    # Update payment
    old_status = payment.status
    payment.status = PaymentRequest.STATUS_TIMED_OUT
    payment.status_reason = f"NOT_PAID_WITHIN_{settings.payment_monitor_seconds}S"
    payment.finalized_at = now
    
    # Create event
    event = PaymentEvent(
        payment_request_id=payment.id,
        event_type=PaymentEvent.EVENT_TIMED_OUT,
        old_status=old_status,
        new_status=PaymentRequest.STATUS_TIMED_OUT,
        source=PaymentEvent.SOURCE_WORKER,
        payload={"reason": payment.status_reason},
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
            PaymentRequest.STATUS_TIMED_OUT,
            now,
        ))


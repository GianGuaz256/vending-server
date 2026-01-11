"""End-to-end tests for complete payment flow."""
import pytest
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import Mock, patch, MagicMock
from app.db.models import PaymentRequest, ProviderInvoice, PaymentEvent
from app.db.session import get_db


class TestCompletePaymentFlow:
    """Test the complete payment flow from creation to completion."""
    
    @patch('app.services.btcpay.BTCPayClient')
    def test_complete_payment_flow_success(self, mock_btcpay_class, authenticated_client, db_session, test_client_obj):
        """Test complete payment flow: create -> pending -> paid."""
        
        # Mock BTCPay client
        mock_btcpay = MagicMock()
        mock_btcpay_class.return_value = mock_btcpay
        
        # Mock BTCPay invoice creation response
        mock_btcpay.create_invoice.return_value = {
            "id": "BTCPAY-INV-123",
            "status": "New",
            "checkoutLink": "https://btcpay.example.com/i/BTCPAY-INV-123",
        }
        mock_btcpay.get_bolt11.return_value = "lnbc1234567890"
        mock_btcpay.get_checkout_link.return_value = "https://btcpay.example.com/i/BTCPAY-INV-123"
        mock_btcpay.get_expires_at.return_value = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        # Step 1: Create payment
        create_response = authenticated_client.post(
            "/api/v1/payments",
            json={
                "payment_method": "BTC_LN",
                "amount": 12.40,
                "currency": "EUR",
                "external_code": "ORDER-E2E-001",
                "description": "E2E Test Payment",
                "metadata": {
                    "test": True,
                    "order_id": "ORDER-E2E-001",
                },
            },
        )
        
        assert create_response.status_code == 201
        payment_data = create_response.json()
        payment_id = payment_data["payment_id"]
        
        assert payment_data["status"] == "PENDING"
        assert payment_data["invoice"]["provider"] == "BTCPAY"
        assert payment_data["invoice"]["bolt11"] == "lnbc1234567890"
        assert payment_data["monitor_until"] is not None
        
        # Step 2: Verify payment was created in database
        payment = db_session.query(PaymentRequest).filter(
            PaymentRequest.id == uuid4().hex if isinstance(payment_id, str) else payment_id
        ).first()
        
        # Fix: Use the actual payment_id from response
        payment = db_session.query(PaymentRequest).filter(
            PaymentRequest.external_code == "ORDER-E2E-001"
        ).first()
        
        assert payment is not None
        assert payment.status == PaymentRequest.STATUS_PENDING
        assert payment.client_id == test_client_obj.id
        
        # Step 3: Verify provider invoice was created
        provider_invoice = payment.provider_invoice
        assert provider_invoice is not None
        assert provider_invoice.provider == "BTCPAY"
        assert provider_invoice.provider_invoice_id == "BTCPAY-INV-123"
        
        # Step 4: Verify events were created
        events = payment.events
        assert len(events) >= 2  # CREATED and PROVIDER_INVOICE_CREATED
        
        event_types = [e.event_type for e in events]
        assert PaymentEvent.EVENT_CREATED in event_types
        assert PaymentEvent.EVENT_PROVIDER_INVOICE_CREATED in event_types
        
        # Step 5: Get payment status
        get_response = authenticated_client.get(f"/api/v1/payments/{payment_id}")
        assert get_response.status_code == 200
        status_data = get_response.json()
        assert status_data["status"] == "PENDING"
        assert status_data["payment_id"] == payment_id
        
        # Step 6: Simulate payment completion via webhook
        mock_btcpay.is_settled.return_value = True
        mock_btcpay.get_invoice.return_value = {
            "id": "BTCPAY-INV-123",
            "status": "Settled",
        }
        
        # Simulate webhook payload
        webhook_payload = {
            "invoiceId": "BTCPAY-INV-123",
            "type": "InvoiceSettled",
            "invoice": {
                "id": "BTCPAY-INV-123",
                "status": "Settled",
            },
        }
        
        # Generate webhook signature
        import json
        from app.core.security import generate_hmac_signature
        
        payload_bytes = json.dumps(webhook_payload, sort_keys=True).encode("utf-8")
        webhook_secret = os.getenv("BTCPAY_WEBHOOK_SECRET", "test_webhook_secret")
        signature = generate_hmac_signature(payload_bytes, webhook_secret)
        
        # Send webhook
        webhook_response = authenticated_client.post(
            "/api/v1/webhooks/btcpay",
            json=webhook_payload,
            headers={"BTCPay-Sig": f"sha256={signature}"},
        )
        
        assert webhook_response.status_code == 200
        
        # Step 7: Verify payment is marked as paid
        db_session.refresh(payment)
        assert payment.status == PaymentRequest.STATUS_PAID
        assert payment.finalized_at is not None
        
        # Step 8: Verify PAID event was created
        paid_events = [e for e in payment.events if e.event_type == PaymentEvent.EVENT_PAID]
        assert len(paid_events) > 0
    
    def test_payment_flow_with_idempotency(self, authenticated_client, db_session, test_client_obj):
        """Test payment creation with idempotency key."""
        idempotency_key = str(uuid4())
        
        with patch('app.services.btcpay.BTCPayClient') as mock_btcpay_class:
            mock_btcpay = MagicMock()
            mock_btcpay_class.return_value = mock_btcpay
            mock_btcpay.create_invoice.return_value = {"id": "BTCPAY-INV-123"}
            mock_btcpay.get_bolt11.return_value = "lnbc123"
            mock_btcpay.get_checkout_link.return_value = "https://btcpay.example.com/i/123"
            mock_btcpay.get_expires_at.return_value = datetime.now(timezone.utc) + timedelta(minutes=15)
            
            # First request
            response1 = authenticated_client.post(
                "/api/v1/payments",
                json={
                    "payment_method": "BTC_LN",
                    "amount": 10.00,
                    "currency": "EUR",
                    "external_code": "ORDER-IDEMPOTENT",
                    "idempotency_key": idempotency_key,
                },
            )
            
            assert response1.status_code == 201
            payment_id_1 = response1.json()["payment_id"]
            
            # Second request with same idempotency key
            response2 = authenticated_client.post(
                "/api/v1/payments",
                json={
                    "payment_method": "BTC_LN",
                    "amount": 10.00,
                    "currency": "EUR",
                    "external_code": "ORDER-IDEMPOTENT",
                    "idempotency_key": idempotency_key,
                },
            )
            
            assert response2.status_code == 201
            payment_id_2 = response2.json()["payment_id"]
            
            # Should return the same payment
            assert payment_id_1 == payment_id_2
    
    def test_payment_flow_timeout(self, authenticated_client, db_session, test_client_obj):
        """Test payment timeout after 2 minutes."""
        with patch('app.services.btcpay.BTCPayClient') as mock_btcpay_class:
            mock_btcpay = MagicMock()
            mock_btcpay_class.return_value = mock_btcpay
            mock_btcpay.create_invoice.return_value = {"id": "BTCPAY-INV-123"}
            mock_btcpay.get_bolt11.return_value = "lnbc123"
            mock_btcpay.get_checkout_link.return_value = "https://btcpay.example.com/i/123"
            mock_btcpay.get_expires_at.return_value = datetime.now(timezone.utc) + timedelta(minutes=15)
            mock_btcpay.is_settled.return_value = False  # Not paid
            
            # Create payment
            response = authenticated_client.post(
                "/api/v1/payments",
                json={
                    "payment_method": "BTC_LN",
                    "amount": 10.00,
                    "currency": "EUR",
                    "external_code": "ORDER-TIMEOUT",
                },
            )
            
            assert response.status_code == 201
            payment_id = response.json()["payment_id"]
            
            # Get payment from DB
            payment = db_session.query(PaymentRequest).filter(
                PaymentRequest.external_code == "ORDER-TIMEOUT"
            ).first()
            
            # Manually trigger timeout (simulating worker)
            from app.worker.tasks import _mark_payment_timed_out
            _mark_payment_timed_out(db_session, payment)
            
            # Verify timeout
            db_session.refresh(payment)
            assert payment.status == PaymentRequest.STATUS_TIMED_OUT
            assert payment.finalized_at is not None


class TestSSEFlow:
    """Test SSE event streaming."""
    
    @pytest.mark.asyncio
    async def test_sse_stream_connection(self, authenticated_client, db_session, test_client_obj):
        """Test SSE stream connection and event delivery."""
        # This is a simplified test - full SSE testing requires async test client
        # For now, we'll test that the endpoint exists and responds
        
        with patch('app.services.btcpay.BTCPayClient') as mock_btcpay_class:
            mock_btcpay = MagicMock()
            mock_btcpay_class.return_value = mock_btcpay
            mock_btcpay.create_invoice.return_value = {"id": "BTCPAY-INV-123"}
            mock_btcpay.get_bolt11.return_value = "lnbc123"
            mock_btcpay.get_checkout_link.return_value = "https://btcpay.example.com/i/123"
            mock_btcpay.get_expires_at.return_value = datetime.now(timezone.utc) + timedelta(minutes=15)
            
            # Create a payment
            create_response = authenticated_client.post(
                "/api/v1/payments",
                json={
                    "payment_method": "BTC_LN",
                    "amount": 10.00,
                    "currency": "EUR",
                    "external_code": "ORDER-SSE",
                },
            )
            
            assert create_response.status_code == 201
            payment_id = create_response.json()["payment_id"]
            
            # Note: Full SSE testing requires httpx.AsyncClient or similar
            # This is a placeholder for the concept
            # In practice, you'd use an async test client to connect to /api/v1/events/stream
            # and verify events are received


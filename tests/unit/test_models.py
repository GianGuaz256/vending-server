"""Unit tests for database models."""
import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from app.db.models import Client, PaymentRequest, ProviderInvoice, PaymentEvent


class TestClientModel:
    """Test Client model."""
    
    def test_create_client(self, db_session):
        """Test creating a client."""
        client = Client(
            id=uuid4(),
            machine_id="TEST-KIOSK-001",
            password_hash="hashed_password",
            is_active=True,
        )
        db_session.add(client)
        db_session.commit()
        
        assert client.id is not None
        assert client.machine_id == "TEST-KIOSK-001"
        assert client.is_active is True
        assert client.created_at is not None
    
    def test_client_unique_machine_id(self, db_session):
        """Test that machine_id must be unique."""
        client1 = Client(
            id=uuid4(),
            machine_id="DUPLICATE",
            password_hash="hash1",
        )
        client2 = Client(
            id=uuid4(),
            machine_id="DUPLICATE",
            password_hash="hash2",
        )
        
        db_session.add(client1)
        db_session.commit()
        
        db_session.add(client2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()


class TestPaymentRequestModel:
    """Test PaymentRequest model."""
    
    def test_create_payment_request(self, db_session, test_client_obj):
        """Test creating a payment request."""
        payment = PaymentRequest(
            id=uuid4(),
            client_id=test_client_obj.id,
            external_code="ORDER-123",
            payment_method="BTC_LN",
            amount=12.40,
            currency="EUR",
            status=PaymentRequest.STATUS_CREATED,
            monitor_until=datetime.now(timezone.utc) + timedelta(seconds=120),
        )
        db_session.add(payment)
        db_session.commit()
        
        assert payment.id is not None
        assert payment.client_id == test_client_obj.id
        assert payment.external_code == "ORDER-123"
        assert payment.status == PaymentRequest.STATUS_CREATED
    
    def test_payment_status_transitions(self, db_session, test_client_obj):
        """Test payment status transitions."""
        payment = PaymentRequest(
            id=uuid4(),
            client_id=test_client_obj.id,
            external_code="ORDER-123",
            payment_method="BTC_LN",
            amount=12.40,
            currency="EUR",
            status=PaymentRequest.STATUS_CREATED,
            monitor_until=datetime.now(timezone.utc) + timedelta(seconds=120),
        )
        db_session.add(payment)
        db_session.commit()
        
        # Transition to PENDING
        payment.status = PaymentRequest.STATUS_PENDING
        db_session.commit()
        assert payment.status == PaymentRequest.STATUS_PENDING
        
        # Transition to PAID
        payment.status = PaymentRequest.STATUS_PAID
        payment.finalized_at = datetime.now(timezone.utc)
        db_session.commit()
        assert payment.status == PaymentRequest.STATUS_PAID
        assert payment.finalized_at is not None


class TestProviderInvoiceModel:
    """Test ProviderInvoice model."""
    
    def test_create_provider_invoice(self, db_session, test_client_obj):
        """Test creating a provider invoice."""
        payment = PaymentRequest(
            id=uuid4(),
            client_id=test_client_obj.id,
            external_code="ORDER-123",
            payment_method="BTC_LN",
            amount=12.40,
            currency="EUR",
            status=PaymentRequest.STATUS_PENDING,
            monitor_until=datetime.now(timezone.utc) + timedelta(seconds=120),
        )
        db_session.add(payment)
        db_session.flush()
        
        invoice = ProviderInvoice(
            id=uuid4(),
            payment_request_id=payment.id,
            provider=ProviderInvoice.PROVIDER_BTCPAY,
            provider_invoice_id="BTCPAY-INV-123",
            store_id="store123",
            checkout_link="https://btcpay.example.com/i/...",
            bolt11="lnbc1...",
            raw_create_response={"id": "BTCPAY-INV-123"},
        )
        db_session.add(invoice)
        db_session.commit()
        
        assert invoice.id is not None
        assert invoice.payment_request_id == payment.id
        assert invoice.provider == "BTCPAY"


class TestPaymentEventModel:
    """Test PaymentEvent model."""
    
    def test_create_payment_event(self, db_session, test_client_obj):
        """Test creating a payment event."""
        payment = PaymentRequest(
            id=uuid4(),
            client_id=test_client_obj.id,
            external_code="ORDER-123",
            payment_method="BTC_LN",
            amount=12.40,
            currency="EUR",
            status=PaymentRequest.STATUS_CREATED,
            monitor_until=datetime.now(timezone.utc) + timedelta(seconds=120),
        )
        db_session.add(payment)
        db_session.flush()
        
        event = PaymentEvent(
            id=uuid4(),
            payment_request_id=payment.id,
            event_type=PaymentEvent.EVENT_CREATED,
            old_status=None,
            new_status=PaymentRequest.STATUS_CREATED,
            source=PaymentEvent.SOURCE_API,
            payload={"test": True},
        )
        db_session.add(event)
        db_session.commit()
        
        assert event.id is not None
        assert event.payment_request_id == payment.id
        assert event.event_type == PaymentEvent.EVENT_CREATED


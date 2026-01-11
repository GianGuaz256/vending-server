"""Pytest configuration and fixtures."""
import os
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set test environment variables before importing app
# Use SQLite for unit tests (faster, no external dependencies)
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["JWT_PRIVATE_KEY_PATH"] = "./tests/fixtures/jwt_private.pem"
os.environ["JWT_PUBLIC_KEY_PATH"] = "./tests/fixtures/jwt_public.pem"
os.environ["JWT_ALGORITHM"] = "RS256"
os.environ["JWT_EXPIRE_MINUTES"] = "10"
os.environ["BTCPAY_BASE_URL"] = "https://test-btcpay.example.com"
os.environ["BTCPAY_API_KEY"] = "test_api_key"
os.environ["BTCPAY_STORE_ID"] = "test_store_id"
os.environ["BTCPAY_WEBHOOK_SECRET"] = "test_webhook_secret"
os.environ["PAYMENT_MONITOR_SECONDS"] = "120"
os.environ["PAYMENT_POLL_INTERVAL_SECONDS"] = "5"

from app.db.session import Base, get_db
from app.db.models import Client, PaymentRequest, ProviderInvoice, PaymentEvent
from app.core.security import hash_password
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="function")
def db_session():
    """Create a test database session."""
    # Use in-memory SQLite for tests (or separate test PostgreSQL)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Override get_db dependency with test session."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_client_obj(db_session):
    """Create a test client in the database."""
    client = Client(
        id=uuid4(),
        machine_id="TEST-KIOSK-001",
        password_hash=hash_password("test_password"),
        is_active=True,
        metadata={"test": True},
    )
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    return client


@pytest.fixture
def auth_token(client, test_client_obj):
    """Get authentication token for test client."""
    response = client.post(
        "/api/v1/auth/token",
        json={
            "machine_id": "TEST-KIOSK-001",
            "password": "test_password",
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def authenticated_client(client, auth_token):
    """Get authenticated test client."""
    client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return client


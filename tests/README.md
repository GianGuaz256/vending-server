# Testing Guide

## Setup

### 1. Install Test Dependencies

```bash
# Make sure you're in the project root with venv activated
pip install pytest pytest-asyncio httpx
```

### 2. Set Up Test Database

For unit tests, we use SQLite in-memory database (configured in `conftest.py`).

For integration tests, you may want to use a separate PostgreSQL database:

```bash
createdb test_vending_db
```

Update `tests/conftest.py` if needed to use PostgreSQL instead of SQLite.

### 3. Generate Test JWT Keys

```bash
# Create test keys in fixtures directory
mkdir -p tests/fixtures
openssl genrsa -out tests/fixtures/jwt_private.pem 2048
openssl rsa -in tests/fixtures/jwt_private.pem -pubout -out tests/fixtures/jwt_public.pem
```

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Unit Tests Only

```bash
pytest tests/unit/
```

### Run End-to-End Tests Only

```bash
pytest tests/e2e/
```

### Run Specific Test File

```bash
pytest tests/unit/test_security.py
```

### Run with Verbose Output

```bash
pytest -v
```

### Run with Coverage

```bash
pip install pytest-cov
pytest --cov=app --cov-report=html
```

## Test Structure

```
tests/
├── conftest.py              # Pytest fixtures and configuration
├── unit/                    # Unit tests
│   ├── test_security.py    # Security module tests
│   ├── test_models.py      # Database model tests
│   └── test_auth.py        # Authentication endpoint tests
└── e2e/                     # End-to-end tests
    └── test_payment_flow.py # Complete payment flow tests
```

## Writing Tests

### Unit Test Example

```python
def test_example(db_session):
    """Test description."""
    # Arrange
    # Act
    # Assert
    assert True
```

### E2E Test Example

```python
def test_payment_creation(authenticated_client):
    """Test payment creation."""
    response = authenticated_client.post(
        "/api/v1/payments",
        json={
            "payment_method": "BTC_LN",
            "amount": 10.00,
            "currency": "EUR",
            "external_code": "TEST-001",
        },
    )
    assert response.status_code == 201
```

## Available Fixtures

- `db_session`: Database session for tests
- `client`: FastAPI test client
- `test_client_obj`: Test client object in database
- `auth_token`: JWT token for authentication
- `authenticated_client`: Test client with authentication headers

## Mocking External Services

Tests use mocks for:
- BTCPay Server API calls
- Redis pub/sub (for unit tests)
- External HTTP requests

See `tests/e2e/test_payment_flow.py` for examples of mocking BTCPay.


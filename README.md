# Vending Payment Server

Production-ready Bitcoin Lightning payment server using FastAPI, Celery, PostgreSQL, and Redis.

## Features

- JWT authentication (10-minute expiry)
- BTCPay Server integration for Lightning payments
- Real-time SSE updates for payment status
- 2-minute payment monitoring window
- Idempotent payment creation
- Webhook support for BTCPay events
- Rate limiting and security hardening

## Quick Start

1. **Create and activate virtual environment** (required):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and configure:
   - Database connection
   - Redis connection
   - JWT keys (RS256)
   - BTCPay credentials

4. Generate JWT keys:
   ```bash
   ./scripts/generate_jwt_keys.sh
   ```

5. Run database migrations:
   ```bash
   alembic upgrade head
   ```

6. Create initial client:
   ```bash
   python scripts/create_client.py --machine-id KIOSK-001 --password secret123
   ```

7. Start services:
   ```bash
   # Option A: Docker Compose
   docker-compose up -d
   
   # Option B: Manual
   uvicorn app.main:app --reload  # Terminal 1
   celery -A app.worker.celery_app worker --loglevel=info  # Terminal 2
   ```

**See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed instructions.**

## API Endpoints

- `GET /health` - Health check
- `POST /auth/token` - Authenticate and get JWT
- `POST /payments` - Create payment
- `GET /payments/{id}` - Get payment status
- `GET /events/stream` - SSE stream for payment events
- `POST /webhooks/btcpay` - BTCPay webhook handler

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload

# Start Celery worker
celery -A app.worker.celery_app worker --loglevel=info
```


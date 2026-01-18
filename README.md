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

### Raspberry Pi Deployment (Recommended)

For Raspberry Pi OS 64-bit, use the one-command installer:

```bash
curl -sSL https://raw.githubusercontent.com/GianGuaz256/vending-server/main/scripts/raspberry_bootstrap.sh | bash
```

**See [DEPLOYMENT.md](DEPLOYMENT.md) for complete Raspberry Pi deployment guide.**

### Docker Compose (Any Platform)

1. Clone the repository:
   ```bash
   git clone https://github.com/GianGuaz256/vending-server.git
   cd vending-server
   ```

2. Generate JWT keys:
   ```bash
   bash scripts/generate_jwt_keys.sh
   ```

3. Configure environment:
   ```bash
   cp env.example .env
   nano .env  # Edit with your BTCPay Server credentials
   ```

4. Start services:
   ```bash
   docker compose up -d
   ```

5. Create initial client:
   ```bash
   docker compose exec api python scripts/create_client.py --machine-id KIOSK-001 --password secret123
   ```

### Manual Installation (Development)

1. **Create and activate virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment:
   ```bash
   cp env.example .env
   nano .env  # Edit with your configuration
   ```

4. Generate JWT keys:
   ```bash
   bash scripts/generate_jwt_keys.sh
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
   # Terminal 1: API server
   uvicorn app.main:app --reload
   
   # Terminal 2: Celery worker
   celery -A app.worker.celery_app worker --loglevel=info
   ```

## API Endpoints

- `GET /health` - Health check
- `POST /auth/token` - Authenticate and get JWT
- `POST /payments` - Create payment
- `GET /payments/{id}` - Get payment status
- `GET /events/stream` - SSE stream for payment events
- `POST /webhooks/btcpay` - BTCPay webhook handler

## Documentation

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Complete Raspberry Pi deployment guide
- **[cloudflared/README.md](cloudflared/README.md)** - Cloudflare Tunnel setup
- **[env.example](env.example)** - Environment configuration template

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Client    │────▶│  FastAPI     │────▶│  BTCPay     │
│  (Vending)  │     │  Server      │     │  Server     │
└─────────────┘     └──────────────┘     └─────────────┘
                           │                     │
                           ▼                     │
                    ┌──────────────┐            │
                    │  PostgreSQL  │            │
                    └──────────────┘            │
                           │                     │
                           ▼                     ▼
                    ┌──────────────┐     ┌─────────────┐
                    │    Redis     │◀────│   Celery    │
                    │   (Pub/Sub)  │     │   Worker    │
                    └──────────────┘     └─────────────┘
```

**Payment Flow:**
1. Client authenticates with JWT
2. Client creates payment request
3. API creates Lightning invoice via BTCPay
4. Celery worker monitors payment (polls every 5s for 2 minutes)
5. BTCPay sends webhook when paid
6. Redis pub/sub notifies client via SSE
7. Optional callback to client URL

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

# Run tests
pytest
```

## Production Deployment

For production deployment on Raspberry Pi:

1. **Use the bootstrap script** (see Quick Start above)
2. **Configure Cloudflare Tunnel** for internet exposure
3. **Set up BTCPay webhook** to your public domain
4. **Enable monitoring** (logs, health checks)
5. **Set up backups** (database, JWT keys)

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions.

## Security

- JWT authentication with RS256 (10-minute expiry)
- Argon2id password hashing
- HMAC webhook verification
- Rate limiting (5 auth requests/min, 60 payment requests/min)
- CORS configuration
- IP allowlisting support

## License

MIT

# Raspberry Pi Deployment Guide

Complete guide for deploying the Vending Payment Server on a Raspberry Pi with Raspberry OS 64-bit.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Manual Installation](#manual-installation)
- [Configuration](#configuration)
- [Internet Exposure](#internet-exposure)
- [Monitoring and Maintenance](#monitoring-and-maintenance)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Hardware

- **Raspberry Pi 4** (4GB+ RAM recommended) or **Raspberry Pi 5**
- **32GB+ microSD card** (Class 10 or better)
- **Stable internet connection** (Ethernet recommended)
- **Power supply** (official Raspberry Pi power supply recommended)

### Software

- **Raspberry Pi OS 64-bit** (Bookworm or newer)
- Fresh installation recommended

### External Services

- **BTCPay Server** instance with:
  - API key with `btcpay.store.canmodifyinvoices` permission
  - Store ID
  - Webhook secret
- **Domain name** (for Cloudflare Tunnel)
- **Cloudflare account** (free tier works)

## Quick Start

### One-Command Installation

For a fresh Raspberry Pi, run this single command:

```bash
curl -sSL https://raw.githubusercontent.com/GianGuaz256/vending-server/main/scripts/raspberry_bootstrap.sh | bash
```

This script will:
1. Update system packages
2. Install Docker and Docker Compose
3. Install Cloudflare Tunnel
4. Clone the repository
5. Generate JWT keys
6. Create configuration template
7. Start services
8. Create initial client

**Note**: You'll be prompted to configure BTCPay Server credentials during installation.

### After Installation

1. Configure Cloudflare Tunnel (see [Internet Exposure](#internet-exposure))
2. Configure BTCPay Server webhook
3. Test the API

## Manual Installation

If you prefer to install step-by-step:

### Step 1: Update System

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### Step 2: Install Docker

```bash
# Install dependencies
sudo apt-get install -y ca-certificates curl gnupg

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Set up repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in for group changes to take effect
```

### Step 3: Install Cloudflare Tunnel

```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb
rm cloudflared-linux-arm64.deb
```

### Step 4: Clone Repository

```bash
cd ~
git clone https://github.com/GianGuaz256/vending-server.git
cd vending-server
```

### Step 5: Generate JWT Keys

```bash
bash scripts/generate_jwt_keys.sh
```

This creates:
- `jwt_private.pem` - Private key for signing tokens
- `jwt_public.pem` - Public key for verifying tokens

**Important**: Keep these keys secure and never commit them to version control.

### Step 6: Configure Environment

```bash
cp env.example .env
nano .env
```

Update the following variables:

```env
# BTCPay Server Configuration
BTCPAY_BASE_URL=https://your-btcpay-server.com
BTCPAY_API_KEY=your_api_key_here
BTCPAY_STORE_ID=your_store_id_here
BTCPAY_WEBHOOK_SECRET=your_webhook_secret_here
```

**Getting BTCPay Server credentials:**

1. Go to your BTCPay Server dashboard
2. Navigate to **Store Settings** → **Access Tokens**
3. Click **Create New Token**
4. Select permissions: `btcpay.store.canmodifyinvoices`
5. Copy the API key
6. Get Store ID from **Store Settings** → **General**

### Step 7: Start Services

```bash
docker compose up -d
```

This starts:
- PostgreSQL database
- Redis cache
- FastAPI server (port 8000)
- Celery worker

Check status:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f
```

### Step 8: Create Initial Client

```bash
docker compose exec api python scripts/create_client.py \
  --machine-id KIOSK-001 \
  --password your_secure_password
```

Save the client ID from the output.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://vending_user:vending_pass@postgres:5432/vending_db` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379/0` |
| `JWT_PRIVATE_KEY_PATH` | Path to JWT private key | `./jwt_private.pem` |
| `JWT_PUBLIC_KEY_PATH` | Path to JWT public key | `./jwt_public.pem` |
| `JWT_ALGORITHM` | JWT signing algorithm | `RS256` |
| `JWT_EXPIRE_MINUTES` | JWT token expiration | `10` |
| `BTCPAY_BASE_URL` | BTCPay Server URL | *Required* |
| `BTCPAY_API_KEY` | BTCPay API key | *Required* |
| `BTCPAY_STORE_ID` | BTCPay Store ID | *Required* |
| `BTCPAY_WEBHOOK_SECRET` | Webhook verification secret | *Required* |
| `PAYMENT_MONITOR_SECONDS` | Payment monitoring window | `120` |
| `PAYMENT_POLL_INTERVAL_SECONDS` | BTCPay polling interval | `5` |
| `API_HOST` | API server host | `0.0.0.0` |
| `API_PORT` | API server port | `8000` |
| `LOG_LEVEL` | Logging level | `INFO` |

### Docker Compose Configuration

The `docker-compose.yml` file defines the services. You can customize:

- **Database credentials** - Change `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- **Resource limits** - Add memory/CPU limits for Raspberry Pi
- **Restart policies** - Already set to restart on failure

### Client Management

Create additional clients:

```bash
docker compose exec api python scripts/create_client.py \
  --machine-id KIOSK-002 \
  --password another_password
```

List clients (requires database access):

```bash
docker compose exec postgres psql -U vending_user -d vending_db -c "SELECT id, machine_id, is_active, created_at FROM clients;"
```

Deactivate a client:

```bash
docker compose exec postgres psql -U vending_user -d vending_db -c "UPDATE clients SET is_active = false WHERE machine_id = 'KIOSK-001';"
```

## Internet Exposure

The server needs to be accessible from the internet for:
- External clients to create payments
- BTCPay Server to send webhooks

### Option 1: Cloudflare Tunnel (Recommended)

**Advantages:**
- No port forwarding required
- Free SSL/TLS certificates
- DDoS protection
- Works behind NAT/firewall

**Setup:**

See detailed guide in [cloudflared/README.md](cloudflared/README.md)

Quick steps:

```bash
# 1. Authenticate
cloudflared tunnel login

# 2. Create tunnel
cloudflared tunnel create vending-server

# 3. Configure tunnel
mkdir -p ~/.cloudflared
cp cloudflared/config.yml.example ~/.cloudflared/config.yml
nano ~/.cloudflared/config.yml  # Edit with your tunnel ID and domain

# 4. Route DNS
cloudflared tunnel route dns vending-server your-domain.com

# 5. Install as service
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

### Option 2: Port Forwarding + Dynamic DNS

**Requirements:**
- Router access for port forwarding
- Dynamic DNS service (e.g., DuckDNS, No-IP)

**Steps:**

1. **Set static IP for Raspberry Pi** (in router settings)

2. **Forward port 8000** to Raspberry Pi's local IP

3. **Set up Dynamic DNS:**
   ```bash
   # Example with DuckDNS
   mkdir ~/duckdns
   cd ~/duckdns
   echo "echo url=\"https://www.duckdns.org/update?domains=YOUR_DOMAIN&token=YOUR_TOKEN&ip=\" | curl -k -o ~/duckdns/duck.log -K -" > duck.sh
   chmod 700 duck.sh
   
   # Add to crontab
   (crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1") | crontab -
   ```

4. **Set up reverse proxy with SSL** (recommended):
   ```bash
   # Install nginx
   sudo apt-get install -y nginx certbot python3-certbot-nginx
   
   # Configure nginx
   sudo nano /etc/nginx/sites-available/vending-server
   ```
   
   Add:
   ```nginx
   server {
       listen 80;
       server_name your-domain.duckdns.org;
       
       location / {
           proxy_pass http://localhost:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```
   
   Enable and get SSL:
   ```bash
   sudo ln -s /etc/nginx/sites-available/vending-server /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   sudo certbot --nginx -d your-domain.duckdns.org
   ```

## Monitoring and Maintenance

### Check Service Status

```bash
# Docker services
docker compose ps

# System resources
docker stats

# Cloudflare tunnel (if using)
sudo systemctl status cloudflared
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f worker

# Last 100 lines
docker compose logs --tail=100 api

# Cloudflare tunnel
sudo journalctl -u cloudflared -f
```

### Database Backup

```bash
# Create backup
docker compose exec postgres pg_dump -U vending_user vending_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore backup
docker compose exec -T postgres psql -U vending_user vending_db < backup_20240115_120000.sql
```

### Update Application

```bash
cd ~/vending-server
git pull
docker compose down
docker compose build
docker compose up -d
```

### Restart Services

```bash
# Restart all services
docker compose restart

# Restart specific service
docker compose restart api
docker compose restart worker
```

### Monitor Payment Activity

```bash
# View recent payments
docker compose exec postgres psql -U vending_user -d vending_db -c "SELECT id, external_code, status, amount, currency, created_at FROM payment_requests ORDER BY created_at DESC LIMIT 10;"

# View payment events
docker compose exec postgres psql -U vending_user -d vending_db -c "SELECT pe.seq, pe.event_type, pe.created_at, pr.external_code FROM payment_events pe JOIN payment_requests pr ON pe.payment_request_id = pr.id ORDER BY pe.seq DESC LIMIT 20;"
```

### System Resources

Monitor Raspberry Pi resources:

```bash
# CPU and memory
htop

# Disk usage
df -h

# Docker disk usage
docker system df
```

Clean up Docker:

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Full cleanup
docker system prune -a --volumes
```

## Troubleshooting

### API Not Responding

**Check if services are running:**
```bash
docker compose ps
```

**Check API logs:**
```bash
docker compose logs api
```

**Common issues:**
- Database not ready: Wait 10-20 seconds after starting
- JWT keys missing: Run `bash scripts/generate_jwt_keys.sh`
- Port conflict: Check if port 8000 is already in use

### Database Connection Errors

**Check PostgreSQL status:**
```bash
docker compose logs postgres
```

**Test connection:**
```bash
docker compose exec postgres psql -U vending_user -d vending_db -c "SELECT 1;"
```

**Reset database:**
```bash
docker compose down -v  # WARNING: This deletes all data
docker compose up -d
```

### BTCPay Integration Issues

**Test BTCPay connection:**
```bash
# From inside the API container
docker compose exec api python -c "
from app.services.btcpay import get_btcpay_client
client = get_btcpay_client()
print(client.client.get('/api/v1/stores').json())
"
```

**Common issues:**
- Invalid API key: Verify in BTCPay Server settings
- Wrong store ID: Check Store Settings → General
- Network connectivity: Ensure Raspberry Pi can reach BTCPay Server
- Webhook not working: Verify webhook secret matches

### Celery Worker Not Processing

**Check worker logs:**
```bash
docker compose logs worker
```

**Check Redis connection:**
```bash
docker compose exec redis redis-cli ping
```

**Restart worker:**
```bash
docker compose restart worker
```

### Cloudflare Tunnel Issues

**Check tunnel status:**
```bash
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -f
```

**Test local API:**
```bash
curl http://localhost:8000/health
```

**Test public URL:**
```bash
curl https://your-domain.com/health
```

**Common issues:**
- Tunnel not connecting: Check credentials file path in config
- DNS not resolving: Wait for propagation (up to 5 minutes)
- 502 Bad Gateway: Ensure API is running on localhost:8000

### Performance Issues

**Reduce resource usage:**

Edit `docker-compose.yml` to limit resources:

```yaml
api:
  deploy:
    resources:
      limits:
        cpus: '1.0'
        memory: 512M
```

**Reduce worker concurrency:**

```yaml
worker:
  command: ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
```

**Use lighter PostgreSQL settings:**

```yaml
postgres:
  command: postgres -c shared_buffers=128MB -c max_connections=50
```

## Security Best Practices

1. **Change default passwords** in `docker-compose.yml`
2. **Use strong client passwords** when creating clients
3. **Rotate JWT keys periodically**
4. **Keep system updated**: `sudo apt-get update && sudo apt-get upgrade`
5. **Monitor logs** for suspicious activity
6. **Enable firewall**: `sudo ufw enable && sudo ufw allow 22`
7. **Use Cloudflare WAF** if using Cloudflare Tunnel
8. **Backup regularly** (database and JWT keys)

## Support

- **Documentation**: [README.md](README.md)
- **Cloudflare Tunnel**: [cloudflared/README.md](cloudflared/README.md)
- **Issues**: [GitHub Issues](https://github.com/GianGuaz256/vending-server/issues)

## Appendix

### Systemd Service (Alternative to Docker Compose)

If you prefer to run as a systemd service instead of Docker Compose:

```bash
sudo nano /etc/systemd/system/vending-server.service
```

Add:

```ini
[Unit]
Description=Vending Payment Server
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/pi/vending-server
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=pi

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable vending-server
sudo systemctl start vending-server
```

### Monitoring with Prometheus/Grafana

For production monitoring, consider setting up Prometheus and Grafana. Add to `docker-compose.yml`:

```yaml
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
  
  grafana:
    image: grafana/grafana
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin

volumes:
  prometheus_data:
  grafana_data:
```


# Cloudflare Tunnel Setup Guide

This guide explains how to expose your Vending Payment Server to the internet using Cloudflare Tunnel (formerly Argo Tunnel).

## Why Cloudflare Tunnel?

- **No port forwarding required** - Works behind NAT/firewall
- **Free** - No cost for the tunnel service
- **Secure** - Encrypted connection, DDoS protection
- **Easy DNS** - Automatic DNS management
- **SSL/TLS** - Free SSL certificates

## Prerequisites

- A domain name (can be registered through Cloudflare or any registrar)
- Cloudflare account (free tier works)
- Domain added to Cloudflare (nameservers pointed to Cloudflare)

## Installation

The bootstrap script already installed `cloudflared`. If you need to install it manually:

```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb
```

## Setup Steps

### 1. Authenticate with Cloudflare

```bash
cloudflared tunnel login
```

This will open a browser window. Log in to Cloudflare and select the domain you want to use.

### 2. Create a Tunnel

```bash
cloudflared tunnel create vending-server
```

This creates a tunnel and generates a credentials file. Note the **Tunnel ID** from the output.

### 3. Configure the Tunnel

Create the configuration directory:

```bash
mkdir -p ~/.cloudflared
```

Copy the example config and edit it:

```bash
cp ~/vending-server/cloudflared/config.yml.example ~/.cloudflared/config.yml
nano ~/.cloudflared/config.yml
```

Replace the following placeholders:
- `YOUR-TUNNEL-ID` - The tunnel ID from step 2
- `YOUR-DOMAIN.com` - Your actual domain

Example configuration:

```yaml
tunnel: abc123-def456-ghi789
credentials-file: /home/pi/.cloudflared/abc123-def456-ghi789.json

ingress:
  - hostname: vending.example.com
    service: http://localhost:8000
    originRequest:
      noTLSVerify: true
      connectTimeout: 30s
  - service: http_status:404
```

### 4. Route DNS to Your Tunnel

```bash
cloudflared tunnel route dns vending-server vending.example.com
```

Replace `vending.example.com` with your actual domain/subdomain.

### 5. Test the Tunnel

Start the tunnel manually to test:

```bash
cloudflared tunnel run vending-server
```

In another terminal, check if it's working:

```bash
curl https://vending.example.com/health
```

You should see a JSON response with the health status.

### 6. Install as a System Service

To run the tunnel automatically on boot:

```bash
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

Check the status:

```bash
sudo systemctl status cloudflared
```

View logs:

```bash
sudo journalctl -u cloudflared -f
```

## Configure BTCPay Server Webhook

Now that your server is accessible via HTTPS, configure BTCPay Server to send webhooks:

1. Go to your BTCPay Server dashboard
2. Navigate to **Store Settings** → **Webhooks**
3. Click **Create Webhook**
4. Configure:
   - **Payload URL**: `https://vending.example.com/api/v1/webhooks/btcpay`
   - **Secret**: Use the value from `BTCPAY_WEBHOOK_SECRET` in your `.env` file
   - **Events**: Select "Invoice settled", "Invoice expired", "Invoice invalid"
   - **Automatic redelivery**: Enable
5. Save the webhook

## Verify Setup

Test the complete flow:

1. **Health check**:
   ```bash
   curl https://vending.example.com/health
   ```

2. **Authentication** (replace credentials):
   ```bash
   curl -X POST https://vending.example.com/api/v1/auth/token \
     -H "Content-Type: application/json" \
     -d '{"machine_id": "KIOSK-001", "password": "your_password"}'
   ```

3. **Create payment** (replace TOKEN):
   ```bash
   curl -X POST https://vending.example.com/api/v1/payments \
     -H "Authorization: Bearer TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "external_code": "ORDER-001",
       "payment_method": "BTC_LN",
       "amount": "1.50",
       "currency": "EUR",
       "description": "Test payment"
     }'
   ```

## Troubleshooting

### Tunnel not connecting

Check the logs:
```bash
sudo journalctl -u cloudflared -f
```

Verify the tunnel exists:
```bash
cloudflared tunnel list
```

### DNS not resolving

Wait a few minutes for DNS propagation. Check DNS:
```bash
dig vending.example.com
```

### 502 Bad Gateway

- Ensure the API server is running: `docker compose ps`
- Check API logs: `docker compose logs api`
- Verify the service URL in config.yml is correct

### Webhooks not working

- Verify webhook secret matches between BTCPay and `.env`
- Check API logs for webhook errors: `docker compose logs api -f`
- Test webhook manually from BTCPay Server webhook settings

## Security Recommendations

1. **Use a dedicated subdomain** - e.g., `vending-api.example.com`
2. **Enable Cloudflare WAF** - Add firewall rules in Cloudflare dashboard
3. **Rate limiting** - Already configured in the application
4. **Monitor logs** - Regularly check for suspicious activity
5. **Rotate secrets** - Periodically update JWT keys and webhook secrets

## Alternative: Running Tunnel in Docker

You can also run cloudflared as a Docker container. Add to `docker-compose.yml`:

```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    command: tunnel --no-autoupdate run --token YOUR_TUNNEL_TOKEN
    restart: unless-stopped
    depends_on:
      - api
```

Get your tunnel token:
```bash
cloudflared tunnel token vending-server
```

## Resources

- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Cloudflared GitHub](https://github.com/cloudflare/cloudflared)


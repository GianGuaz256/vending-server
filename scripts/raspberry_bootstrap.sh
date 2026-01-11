#!/bin/bash
#
# Raspberry Pi Bootstrap Script for Vending Payment Server
# This script sets up a fresh Raspberry Pi OS 64-bit system with all dependencies
#
# Usage: curl -sSL https://raw.githubusercontent.com/GianGuaz256/vending-server/main/scripts/raspberry_bootstrap.sh | bash
#

set -e  # Exit on error

echo "=========================================="
echo "Vending Payment Server - Raspberry Pi Setup"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo -e "${RED}ERROR: Please do not run this script as root${NC}"
   echo "Run as regular user: bash raspberry_bootstrap.sh"
   exit 1
fi

# Function to print status
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Update system
echo ""
echo "Step 1: Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y
print_status "System updated"

# Install dependencies
echo ""
echo "Step 2: Installing dependencies..."
sudo apt-get install -y \
    git \
    curl \
    wget \
    ca-certificates \
    gnupg \
    lsb-release \
    openssl
print_status "Dependencies installed"

# Install Docker
echo ""
echo "Step 3: Installing Docker..."
if command -v docker &> /dev/null; then
    print_warning "Docker already installed, skipping..."
else
    # Add Docker's official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    
    # Set up Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker Engine
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Add current user to docker group
    sudo usermod -aG docker $USER
    print_status "Docker installed"
    print_warning "You may need to log out and back in for docker group membership to take effect"
fi

# Install Cloudflare Tunnel
echo ""
echo "Step 4: Installing Cloudflare Tunnel (cloudflared)..."
if command -v cloudflared &> /dev/null; then
    print_warning "cloudflared already installed, skipping..."
else
    # Download and install cloudflared for ARM64
    wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
    sudo dpkg -i cloudflared-linux-arm64.deb
    rm cloudflared-linux-arm64.deb
    print_status "Cloudflare Tunnel installed"
fi

# Clone repository
echo ""
echo "Step 5: Cloning repository..."
REPO_DIR="$HOME/vending-server"
if [ -d "$REPO_DIR" ]; then
    print_warning "Repository directory already exists at $REPO_DIR"
    read -p "Do you want to remove it and re-clone? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$REPO_DIR"
        git clone https://github.com/GianGuaz256/vending-server.git "$REPO_DIR"
        print_status "Repository cloned"
    else
        print_warning "Using existing repository"
    fi
else
    git clone https://github.com/GianGuaz256/vending-server.git "$REPO_DIR"
    print_status "Repository cloned"
fi

cd "$REPO_DIR"

# Generate JWT keys
echo ""
echo "Step 6: Generating JWT keys..."
if [ -f "jwt_private.pem" ] && [ -f "jwt_public.pem" ]; then
    print_warning "JWT keys already exist, skipping generation..."
else
    bash scripts/generate_jwt_keys.sh
    print_status "JWT keys generated"
fi

# Create .env file
echo ""
echo "Step 7: Creating environment configuration..."
if [ -f ".env" ]; then
    print_warning ".env file already exists"
    read -p "Do you want to reconfigure it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_warning "Skipping .env configuration"
    else
        cp env.example .env
        echo ""
        echo "Please edit .env file with your BTCPay Server credentials:"
        echo "  nano .env"
        echo ""
        read -p "Press Enter when you're done editing .env..."
    fi
else
    cp env.example .env
    echo ""
    print_warning "IMPORTANT: You need to configure your .env file with BTCPay Server credentials"
    echo ""
    echo "Required configuration:"
    echo "  - BTCPAY_BASE_URL: Your BTCPay Server URL"
    echo "  - BTCPAY_API_KEY: API key from BTCPay Server"
    echo "  - BTCPAY_STORE_ID: Your store ID"
    echo "  - BTCPAY_WEBHOOK_SECRET: Secret for webhook verification"
    echo ""
    read -p "Do you want to edit .env now? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        nano .env
    fi
fi

# Start services
echo ""
echo "Step 8: Starting Docker services..."
print_warning "This will start PostgreSQL, Redis, API, and Celery worker"
read -p "Do you want to start the services now? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    # Use newgrp to apply docker group without logout (if needed)
    if groups | grep -q docker; then
        docker compose up -d
    else
        print_warning "Running with sudo since docker group not yet active"
        sudo docker compose up -d
    fi
    
    # Wait for services to start
    echo "Waiting for services to start..."
    sleep 10
    
    print_status "Services started"
    echo ""
    echo "Checking service status..."
    if groups | grep -q docker; then
        docker compose ps
    else
        sudo docker compose ps
    fi
fi

# Create initial client
echo ""
echo "Step 9: Creating initial client..."
read -p "Do you want to create an initial client now? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    read -p "Enter machine ID (e.g., KIOSK-001): " MACHINE_ID
    read -sp "Enter password: " PASSWORD
    echo
    
    if groups | grep -q docker; then
        docker compose exec api python scripts/create_client.py --machine-id "$MACHINE_ID" --password "$PASSWORD"
    else
        sudo docker compose exec api python scripts/create_client.py --machine-id "$MACHINE_ID" --password "$PASSWORD"
    fi
    print_status "Client created"
fi

# Cloudflare Tunnel setup
echo ""
echo "=========================================="
echo "Step 10: Cloudflare Tunnel Setup"
echo "=========================================="
echo ""
echo "To expose your server to the internet via Cloudflare Tunnel:"
echo ""
echo "1. Authenticate cloudflared:"
echo "   cloudflared tunnel login"
echo ""
echo "2. Create a tunnel:"
echo "   cloudflared tunnel create vending-server"
echo ""
echo "3. Create tunnel configuration:"
echo "   mkdir -p ~/.cloudflared"
echo "   nano ~/.cloudflared/config.yml"
echo ""
echo "4. Add this configuration (replace TUNNEL-ID with your tunnel ID):"
echo ""
echo "   tunnel: TUNNEL-ID"
echo "   credentials-file: /home/$USER/.cloudflared/TUNNEL-ID.json"
echo ""
echo "   ingress:"
echo "     - hostname: your-domain.com"
echo "       service: http://localhost:8000"
echo "     - service: http_status:404"
echo ""
echo "5. Route DNS to your tunnel:"
echo "   cloudflared tunnel route dns vending-server your-domain.com"
echo ""
echo "6. Start the tunnel:"
echo "   cloudflared tunnel run vending-server"
echo ""
echo "Or install as a service:"
echo "   sudo cloudflared service install"
echo ""
print_warning "See DEPLOYMENT.md for detailed Cloudflare Tunnel instructions"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
print_status "Vending Payment Server is installed at: $REPO_DIR"
echo ""
echo "Next steps:"
echo "  1. Configure Cloudflare Tunnel (see above)"
echo "  2. Configure BTCPay Server webhook to point to your domain"
echo "  3. Test the API: curl http://localhost:8000/health"
echo ""
echo "API will be available at:"
echo "  - Local: http://localhost:8000"
echo "  - After Cloudflare setup: https://your-domain.com"
echo ""
echo "Documentation:"
echo "  - README.md - General documentation"
echo "  - DEPLOYMENT.md - Raspberry Pi deployment guide"
echo ""
print_status "All done! 🚀"


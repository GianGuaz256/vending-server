#!/usr/bin/env python3
"""
Simple payment flow test script
Tests authentication and payment creation
"""

import sys
import os
import httpx
from decimal import Decimal
import time
import argparse

# Default configuration
DEFAULT_SERVER_URL = "http://localhost:8000"
DEFAULT_MACHINE_ID = "KIOSK-001"
DEFAULT_PASSWORD = "secret123"

def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def print_success(text):
    """Print success message."""
    print(f"✓ {text}")

def print_error(text):
    """Print error message."""
    print(f"✗ {text}")

def test_health_check(client, server_url):
    """Test server health check."""
    print_header("1. Testing Health Check")
    try:
        response = client.get(f"{server_url}/health")
        response.raise_for_status()
        data = response.json()
        print_success(f"Health check passed: {data}")
        return True
    except Exception as e:
        print_error(f"Health check failed: {e}")
        return False

def test_authentication(client, server_url, machine_id, password):
    """Test authentication and return token."""
    print_header("2. Testing Authentication")
    try:
        response = client.post(
            f"{server_url}/api/v1/auth/token",
            json={
                "machine_id": machine_id,
                "password": password,
                "device_info": {
                    "client": "test_raspberry_payment.py",
                    "version": "1.0.0",
                },
            },
        )
        response.raise_for_status()
        data = response.json()
        token = data["access_token"]
        print_success(f"Authentication successful")
        print(f"  Token expires in: {data['expires_in']} seconds")
        return token
    except httpx.HTTPStatusError as e:
        print_error(f"Authentication failed: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        print_error(f"Authentication error: {e}")
        return None

def test_payment_creation(client, server_url, token):
    """Test payment creation."""
    print_header("3. Testing Payment Creation")
    try:
        external_code = f"TEST-{int(time.time())}"
        response = client.post(
            f"{server_url}/api/v1/payments",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "payment_method": "BTC_LN",
                "amount": "1.00",
                "currency": "EUR",
                "external_code": external_code,
                "description": "Test payment",
                "metadata": {
                    "test": True,
                    "source": "test_script",
                },
            },
        )
        response.raise_for_status()
        data = response.json()
        payment_id = data["payment_id"]
        print_success(f"Payment created successfully")
        print(f"  Payment ID: {payment_id}")
        print(f"  Status: {data['status']}")
        print(f"  External Code: {external_code}")
        
        if data.get("invoice"):
            print(f"  Provider: {data['invoice'].get('provider')}")
            print(f"  Provider Invoice ID: {data['invoice'].get('provider_invoice_id')}")
            if data['invoice'].get('checkout_link'):
                print(f"  Checkout Link: {data['invoice']['checkout_link']}")
        
        if data.get("lightning_invoice"):
            bolt11 = data["lightning_invoice"]
            print(f"  BOLT11 Invoice: {bolt11[:50]}...")
        
        return payment_id
    except httpx.HTTPStatusError as e:
        print_error(f"Payment creation failed: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        print_error(f"Payment creation error: {e}")
        return None

def test_payment_status(client, server_url, token, payment_id):
    """Test payment status retrieval."""
    print_header("4. Testing Payment Status Retrieval")
    try:
        response = client.get(
            f"{server_url}/api/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        data = response.json()
        print_success(f"Payment status retrieved successfully")
        print(f"  Payment ID: {data['payment_id']}")
        print(f"  Status: {data['status']}")
        print(f"  Amount: {data['amount']['amount']} {data['amount']['currency']}")
        print(f"  Created At: {data['created_at']}")
        return True
    except httpx.HTTPStatusError as e:
        print_error(f"Payment status retrieval failed: {e.response.status_code} - {e.response.text}")
        return False
    except Exception as e:
        print_error(f"Payment status error: {e}")
        return False

def main():
    """Run all tests."""
    parser = argparse.ArgumentParser(description="Test payment flow")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL, help="Server URL")
    parser.add_argument("--machine-id", default=DEFAULT_MACHINE_ID, help="Machine ID")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password")
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("  Payment Flow Test")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  Server URL: {args.server_url}")
    print(f"  Machine ID: {args.machine_id}")
    print(f"  Password: {'*' * len(args.password)}")
    
    client = httpx.Client(timeout=30.0)
    
    try:
        # Run tests
        if not test_health_check(client, args.server_url):
            print_error("\nHealth check failed. Is the server running?")
            print("\nTo start the server:")
            print("  1. Start Docker: docker compose up -d")
            print("  OR")
            print("  2. Start manually:")
            print("     Terminal 1: uvicorn app.main:app --reload")
            print("     Terminal 2: celery -A app.worker.celery_app worker --loglevel=info")
            sys.exit(1)
        
        token = test_authentication(client, args.server_url, args.machine_id, args.password)
        if not token:
            print_error("\nAuthentication failed. Check your credentials.")
            print("\nTo create a client:")
            print(f"  python scripts/create_client.py --machine-id {args.machine_id} --password {args.password}")
            sys.exit(1)
        
        payment_id = test_payment_creation(client, args.server_url, token)
        if not payment_id:
            print_error("\nPayment creation failed.")
            sys.exit(1)
        
        if not test_payment_status(client, args.server_url, token, payment_id):
            print_error("\nPayment status retrieval failed.")
            sys.exit(1)
        
        # Summary
        print_header("Test Summary")
        print_success("All tests passed!")
        print("\nNext steps:")
        print("  1. The payment invoice has been created")
        print("  2. You can now test paying it with a Lightning wallet")
        print("  3. Use the client demo for interactive testing:")
        print(f"     python scripts/client_demo.py --server-url {args.server_url} --machine-id {args.machine_id} --password {args.password}")
        print("\n")
        
    finally:
        client.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

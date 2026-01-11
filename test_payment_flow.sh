#!/bin/bash

# Test Payment Flow Script
# This script creates a payment, displays the payment link, and monitors the status

set -e

API_URL="http://localhost:8000"
MACHINE_ID="KIOSK-001"
PASSWORD="secret123"

echo "========================================="
echo "Lightning Payment Flow Test"
echo "========================================="
echo ""

# 1. Authenticate
echo "🔐 Authenticating..."
TOKEN=$(curl -s -X POST "$API_URL/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d "{\"machine_id\": \"$MACHINE_ID\", \"password\": \"$PASSWORD\"}" | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

echo "✓ Authentication successful"
echo ""

# 2. Create payment
echo "💰 Creating payment..."
PAYMENT_RESPONSE=$(curl -s -X POST "$API_URL/api/v1/payments" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "payment_method": "BTC_LN",
    "amount": 1.00,
    "currency": "EUR",
    "external_code": "test_'$(date +%s)'"
  }')

PAYMENT_ID=$(echo $PAYMENT_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['payment_id'])")
CHECKOUT_LINK=$(echo $PAYMENT_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['invoice']['checkout_link'])")
BOLT11=$(echo $PAYMENT_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['lightning_invoice'])")
INITIAL_STATUS=$(echo $PAYMENT_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")

echo "✓ Payment created"
echo ""
echo "📋 Payment Details:"
echo "   Payment ID: $PAYMENT_ID"
echo "   Status: $INITIAL_STATUS"
echo "   Amount: 0.01 EUR"
echo ""
echo "⚡ Lightning Invoice (BOLT11):"
echo "   $BOLT11"
echo ""
echo "🔗 Checkout Link:"
echo "   $CHECKOUT_LINK"
echo ""
echo "========================================="
echo "Please pay the invoice using:"
echo "1. Open the checkout link in your browser, OR"
echo "2. Scan the QR code with a Lightning wallet, OR"
echo "3. Copy the BOLT11 invoice and paste it in your Lightning wallet"
echo "========================================="
echo ""
echo "⏳ Monitoring payment status (press Ctrl+C to stop)..."
echo ""

# 3. Poll payment status
STATUS="$INITIAL_STATUS"
COUNT=0
MAX_ATTEMPTS=60  # 60 attempts = 2 minutes (2-second intervals)

while [ "$STATUS" != "SETTLED" ] && [ "$STATUS" != "EXPIRED" ] && [ "$STATUS" != "INVALID" ] && [ $COUNT -lt $MAX_ATTEMPTS ]; do
  sleep 2
  
  PAYMENT_STATUS=$(curl -s -X GET "$API_URL/api/v1/payments/$PAYMENT_ID" \
    -H "Authorization: Bearer $TOKEN")
  
  STATUS=$(echo $PAYMENT_STATUS | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")
  
  COUNT=$((COUNT + 1))
  
  if [ "$STATUS" = "SETTLED" ]; then
    echo "✅ Payment SETTLED! Payment confirmed."
    FINALIZED_AT=$(echo $PAYMENT_STATUS | python3 -c "import sys, json; print(json.load(sys.stdin).get('finalized_at', 'N/A'))")
    echo "   Finalized at: $FINALIZED_AT"
    break
  elif [ "$STATUS" = "EXPIRED" ]; then
    echo "⏰ Payment EXPIRED. Invoice timed out."
    break
  elif [ "$STATUS" = "INVALID" ]; then
    echo "❌ Payment INVALID. Something went wrong."
    break
  else
    echo "⏳ Status: $STATUS (attempt $COUNT/$MAX_ATTEMPTS)"
  fi
done

if [ $COUNT -ge $MAX_ATTEMPTS ]; then
  echo "⚠️  Timeout: Payment still pending after 2 minutes"
fi

echo ""
echo "========================================="
echo "Test complete!"
echo "========================================="


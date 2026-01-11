# Vending Payment Server API Documentation

OpenAPI 3.0 specification for the Bitcoin Lightning payment server for vending machines.

```yaml
openapi: 3.0.3
info:
  title: Vending Payment Server API
  description: |
    Bitcoin Lightning payment server for vending machines.
    
    This API provides endpoints for:
    - Client authentication using JWT tokens
    - Creating Lightning Network payment invoices
    - Monitoring payment status in real-time
    - Receiving webhook notifications from BTCPay Server
    
    ## Authentication Flow
    1. Client authenticates with machine_id and password
    2. Server returns JWT token (valid for 10 minutes)
    3. Client uses Bearer token for all subsequent requests
    
    ## Payment Flow
    1. Client creates payment request (POST /api/v1/payments)
    2. Server creates BTCPay invoice and returns BOLT11 Lightning invoice
    3. Customer pays the Lightning invoice
    4. Server receives webhook from BTCPay and updates payment status
    5. Client polls payment status or listens to SSE stream for real-time updates
    
  version: 0.1.0
  contact:
    name: API Support
  license:
    name: MIT

servers:
  - url: http://localhost:8000
    description: Local development server
  - url: https://api.example.com
    description: Production server

tags:
  - name: health
    description: Health check endpoints
  - name: authentication
    description: Client authentication and JWT token management
  - name: payments
    description: Payment request creation and status monitoring
  - name: events
    description: Server-Sent Events (SSE) for real-time payment updates
  - name: webhooks
    description: Webhook endpoints for external payment providers

paths:
  /health:
    get:
      tags:
        - health
      summary: Health check
      description: Check API server and database connectivity status
      operationId: healthCheck
      responses:
        '200':
          description: Service is healthy
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [ok, degraded]
                    description: Overall service status
                  database:
                    type: string
                    enum: [ok, degraded]
                    description: Database connectivity status
                  time:
                    type: string
                    format: date-time
                    description: Current server timestamp (ISO 8601)
              example:
                status: ok
                database: ok
                time: "2026-01-11T12:00:00.000Z"

  /api/v1/auth/token:
    post:
      tags:
        - authentication
      summary: Authenticate and obtain JWT token
      description: |
        Authenticate a client using machine_id and password.
        Returns a JWT Bearer token valid for 10 minutes.
        
        **Rate Limit:** 5 requests per minute per IP
      operationId: createToken
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TokenRequest'
            example:
              machine_id: "KIOSK-001"
              password: "secret123"
              device_info:
                os: "Linux"
                version: "1.0.0"
      responses:
        '200':
          description: Authentication successful
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TokenResponse'
              example:
                access_token: "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
                token_type: "bearer"
                expires_in: 600
        '401':
          description: Invalid credentials
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
              example:
                detail: "Invalid credentials"
        '403':
          description: Client is inactive or IP not allowed
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
              example:
                detail: "Client is inactive"
        '429':
          description: Rate limit exceeded
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
              example:
                detail: "Rate limit exceeded"

  /api/v1/payments:
    post:
      tags:
        - payments
      summary: Create a new payment request
      description: |
        Create a new Lightning Network payment invoice.
        
        The server will:
        1. Create a payment request record
        2. Generate a BTCPay Lightning invoice
        3. Return the BOLT11 invoice string and checkout link
        4. Start monitoring the payment status
        
        **Rate Limit:** 60 requests per minute per client
        
        **Idempotency:** Use `idempotency_key` to safely retry requests
      operationId: createPayment
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PaymentCreateRequest'
            example:
              payment_method: "BTC_LN"
              amount: 1.00
              currency: "EUR"
              external_code: "ORDER-12345"
              description: "Coffee purchase"
              metadata:
                product_id: "COFFEE_LARGE"
                location: "KIOSK-001"
      responses:
        '201':
          description: Payment created successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/PaymentResponse'
        '400':
          description: Invalid request parameters
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '401':
          description: Unauthorized - invalid or expired token
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '502':
          description: Failed to create invoice with payment provider
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'

  /api/v1/payments/{payment_id}:
    get:
      tags:
        - payments
      summary: Get payment status
      description: |
        Retrieve the current status of a payment request.
        
        Clients should poll this endpoint every 2-5 seconds to check payment status.
        Alternatively, use the SSE stream endpoint for real-time updates.
      operationId: getPayment
      security:
        - bearerAuth: []
      parameters:
        - name: payment_id
          in: path
          required: true
          description: Payment request UUID
          schema:
            type: string
            format: uuid
          example: "550e8400-e29b-41d4-a716-446655440000"
      responses:
        '200':
          description: Payment details retrieved successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/PaymentResponse'
        '401':
          description: Unauthorized - invalid or expired token
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '404':
          description: Payment not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'

  /api/v1/events/stream:
    get:
      tags:
        - events
      summary: Server-Sent Events stream for real-time payment updates
      description: |
        Subscribe to real-time payment events using Server-Sent Events (SSE).
        
        The stream will send events for all payments belonging to the authenticated client.
        
        **Event Types:**
        - `payment.created` - Payment request created
        - `payment.invoice_created` - Lightning invoice generated
        - `payment.status_changed` - Payment status updated
        - `payment.paid` - Payment successfully received
        - `payment.expired` - Invoice expired
        - `payment.timed_out` - Payment monitoring window ended
        - `payment.failed` - Payment failed
        - `keepalive` - Heartbeat message (every 15 seconds)
        
        **Reconnection:**
        Include the `Last-Event-ID` header to replay missed events after reconnection.
      operationId: eventStream
      security:
        - bearerAuth: []
      parameters:
        - name: Last-Event-ID
          in: header
          required: false
          description: Last received event sequence number for replay
          schema:
            type: integer
          example: 12345
      responses:
        '200':
          description: SSE stream established
          content:
            text/event-stream:
              schema:
                type: string
              example: |
                id: 12346
                event: payment.invoice_created
                data: {"event_id":12346,"event":"payment.invoice_created","emitted_at":"2026-01-11T12:00:00Z","payment":{"payment_id":"550e8400-e29b-41d4-a716-446655440000","status":"PENDING","amount":{"amount":"1.00","currency":"EUR"}}}
                
                event: keepalive
                data: {"ts":"2026-01-11T12:00:15Z"}
        '401':
          description: Unauthorized - invalid or expired token
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'

  /api/v1/webhooks/btcpay:
    post:
      tags:
        - webhooks
      summary: BTCPay Server webhook endpoint
      description: |
        Receive webhook notifications from BTCPay Server.
        
        This endpoint is called by BTCPay Server when invoice status changes.
        The webhook signature is verified using HMAC-SHA256.
        
        **Security:** Requires valid BTCPay-Sig header with HMAC signature
      operationId: btcpayWebhook
      parameters:
        - name: BTCPay-Sig
          in: header
          required: true
          description: HMAC-SHA256 signature (format: sha256=<hex>)
          schema:
            type: string
          example: "sha256=abc123..."
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              description: BTCPay webhook payload (format varies by event type)
            example:
              type: "InvoiceSettled"
              invoiceId: "ABC123"
              invoice:
                id: "ABC123"
                status: "Settled"
      responses:
        '200':
          description: Webhook processed successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [processed, ignored, logged]
                  payment_id:
                    type: string
                    format: uuid
                  reason:
                    type: string
              example:
                status: "processed"
                payment_id: "550e8400-e29b-41d4-a716-446655440000"
        '400':
          description: Invalid webhook payload
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '401':
          description: Invalid or missing signature
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: JWT token obtained from /api/v1/auth/token endpoint

  schemas:
    TokenRequest:
      type: object
      required:
        - machine_id
        - password
      properties:
        machine_id:
          type: string
          minLength: 1
          maxLength: 255
          description: Unique machine identifier
          example: "KIOSK-001"
        password:
          type: string
          minLength: 1
          description: Client password
          format: password
          example: "secret123"
        nonce:
          type: string
          maxLength: 255
          description: Optional client nonce for additional security
          example: "random-nonce-123"
        device_info:
          type: object
          description: Optional device metadata
          additionalProperties: true
          example:
            os: "Linux"
            version: "1.0.0"
            hardware: "Raspberry Pi 4"

    TokenResponse:
      type: object
      required:
        - access_token
        - token_type
        - expires_in
      properties:
        access_token:
          type: string
          description: JWT Bearer token
          example: "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
        token_type:
          type: string
          enum: [bearer]
          description: Token type (always "bearer")
          example: "bearer"
        expires_in:
          type: integer
          description: Token expiration time in seconds
          example: 600

    PaymentCreateRequest:
      type: object
      required:
        - payment_method
        - amount
        - currency
        - external_code
      properties:
        payment_method:
          type: string
          enum: [BTC_LN]
          description: Payment method (currently only Bitcoin Lightning Network)
          example: "BTC_LN"
        amount:
          type: number
          format: decimal
          minimum: 0
          exclusiveMinimum: true
          description: Payment amount
          example: 1.00
        currency:
          type: string
          minLength: 3
          maxLength: 10
          description: Currency code (ISO 4217)
          example: "EUR"
        external_code:
          type: string
          minLength: 1
          maxLength: 64
          description: Merchant order ID or reference code
          example: "ORDER-12345"
        description:
          type: string
          maxLength: 500
          description: Payment description
          example: "Coffee purchase"
        callback_url:
          type: string
          format: uri
          maxLength: 2048
          description: URL to receive payment status callbacks
          example: "https://client.example.com/payment-callback"
        redirect_url:
          type: string
          format: uri
          maxLength: 2048
          description: URL to redirect customer after payment
          example: "https://client.example.com/payment-success"
        metadata:
          type: object
          description: Additional metadata (max 8KB JSON)
          additionalProperties: true
          example:
            product_id: "COFFEE_LARGE"
            location: "KIOSK-001"
        idempotency_key:
          type: string
          maxLength: 255
          description: Idempotency key for safe retries
          example: "ORDER-12345-retry-1"

    PaymentResponse:
      type: object
      required:
        - payment_id
        - status
        - monitor_until
        - invoice
        - amount
        - metadata
        - external_code
        - created_at
      properties:
        payment_id:
          type: string
          format: uuid
          description: Unique payment request ID
          example: "550e8400-e29b-41d4-a716-446655440000"
        status:
          type: string
          enum: [CREATED, PENDING, PAID, EXPIRED, TIMED_OUT, FAILED, CANCELED]
          description: |
            Payment status:
            - CREATED: Payment request created
            - PENDING: Lightning invoice generated, awaiting payment
            - PAID: Payment successfully received
            - EXPIRED: Invoice expired (past BTCPay expiration)
            - TIMED_OUT: Monitoring window ended without payment
            - FAILED: Payment failed
            - CANCELED: Payment canceled by client
          example: "PENDING"
        monitor_until:
          type: string
          format: date-time
          description: Timestamp until which payment is monitored (typically 2 minutes)
          example: "2026-01-11T12:02:00.000Z"
        invoice:
          $ref: '#/components/schemas/InvoiceSchema'
        amount:
          $ref: '#/components/schemas/AmountSchema'
        metadata:
          type: object
          description: Payment metadata
          additionalProperties: true
          example:
            product_id: "COFFEE_LARGE"
        external_code:
          type: string
          description: Merchant order ID
          example: "ORDER-12345"
        created_at:
          type: string
          format: date-time
          description: Payment creation timestamp
          example: "2026-01-11T12:00:00.000Z"
        finalized_at:
          type: string
          format: date-time
          nullable: true
          description: Payment finalization timestamp (when status became final)
          example: "2026-01-11T12:01:30.000Z"
        status_reason:
          type: string
          nullable: true
          description: Additional status information (e.g., error details)
          example: "PROVIDER_EXPIRED"
        lightning_invoice:
          type: string
          nullable: true
          description: BOLT11 Lightning invoice string for QR code display
          example: "lnbc10n1p3..."

    InvoiceSchema:
      type: object
      required:
        - provider
        - provider_invoice_id
      properties:
        provider:
          type: string
          enum: [BTCPAY]
          description: Payment provider
          example: "BTCPAY"
        provider_invoice_id:
          type: string
          description: Provider's invoice ID
          example: "ABC123XYZ"
        checkout_link:
          type: string
          format: uri
          nullable: true
          description: BTCPay checkout page URL
          example: "https://btcpay.example.com/i/ABC123XYZ"
        bolt11:
          type: string
          nullable: true
          description: BOLT11 Lightning invoice string
          example: "lnbc10n1p3..."
        expires_at:
          type: string
          format: date-time
          nullable: true
          description: Invoice expiration timestamp
          example: "2026-01-11T12:15:00.000Z"

    AmountSchema:
      type: object
      required:
        - amount
        - currency
      properties:
        amount:
          type: number
          format: decimal
          description: Payment amount
          example: 1.00
        currency:
          type: string
          description: Currency code
          example: "EUR"

    Error:
      type: object
      required:
        - detail
      properties:
        detail:
          type: string
          description: Error message
          example: "Invalid credentials"

security:
  - bearerAuth: []
```

## Usage Examples

### 1. Health Check

```bash
curl -X GET http://localhost:8000/health
```

### 2. Authenticate

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "machine_id": "KIOSK-001",
    "password": "secret123"
  }'
```

### 3. Create Payment

```bash
TOKEN="your-jwt-token"

curl -X POST http://localhost:8000/api/v1/payments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "payment_method": "BTC_LN",
    "amount": 1.00,
    "currency": "EUR",
    "external_code": "ORDER-12345",
    "description": "Coffee purchase"
  }'
```

### 4. Check Payment Status

```bash
PAYMENT_ID="550e8400-e29b-41d4-a716-446655440000"

curl -X GET http://localhost:8000/api/v1/payments/$PAYMENT_ID \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Subscribe to SSE Stream

```bash
curl -X GET http://localhost:8000/api/v1/events/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream"
```

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| POST /api/v1/auth/token | 5 requests/minute per IP |
| POST /api/v1/payments | 60 requests/minute per client |
| GET /api/v1/payments/{id} | No limit |
| GET /api/v1/events/stream | 1 connection per client |

## Payment Status Flow

```
CREATED → PENDING → PAID (final)
                  ↘ EXPIRED (final)
                  ↘ TIMED_OUT (final)
                  ↘ FAILED (final)
```

## Error Handling

All error responses follow this format:

```json
{
  "detail": "Error message description"
}
```

Common HTTP status codes:
- `400` - Bad Request (invalid parameters)
- `401` - Unauthorized (invalid/expired token)
- `403` - Forbidden (client inactive or IP not allowed)
- `404` - Not Found (resource doesn't exist)
- `429` - Too Many Requests (rate limit exceeded)
- `502` - Bad Gateway (payment provider error)

## Importing to Swagger

To use this specification with Swagger:

1. **Swagger Editor**: Copy the YAML content from this file and paste it into [Swagger Editor](https://editor.swagger.io/)

2. **Swagger UI**: Host the YAML file and point Swagger UI to it:
   ```html
   <div id="swagger-ui"></div>
   <script src="https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js"></script>
   <script>
     SwaggerUIBundle({
       url: '/path/to/API.md',
       dom_id: '#swagger-ui'
     })
   </script>
   ```

3. **Extract YAML only**: If you need just the YAML, extract the content between the triple backticks marked with `yaml`.


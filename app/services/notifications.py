"""Notification service for SSE and callbacks."""
import json
import httpx
from datetime import datetime, timezone
from typing import Optional
import redis

from app.core.config import settings
from app.core.security import generate_hmac_signature

# Redis client for pub/sub
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def publish_payment_event(client_id: str, payment_id: str, event_seq: int):
    """
    Publish payment event notification via Redis pub/sub.
    
    Args:
        client_id: Client UUID
        payment_id: Payment request UUID
        event_seq: Event sequence number
    """
    channel = f"client:{client_id}:events"
    message = json.dumps({
        "payment_id": payment_id,
        "event_seq": event_seq,
    })
    redis_client.publish(channel, message)


async def send_callback(
    callback_url: str,
    payment_id: str,
    status: str,
    finalized_at: Optional[datetime] = None,
    max_retries: int = 3,
) -> bool:
    """
    Send callback notification to client URL with exponential backoff.
    
    Args:
        callback_url: Client callback URL
        payment_id: Payment request UUID
        status: Payment status
        finalized_at: Finalization timestamp
        max_retries: Maximum retry attempts
        
    Returns:
        True if callback succeeded, False otherwise
    """
    payload = {
        "payment_id": str(payment_id),
        "status": status,
        "finalized_at": finalized_at.isoformat() if finalized_at else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    # Generate HMAC signature
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = generate_hmac_signature(payload_bytes, settings.btcpay_webhook_secret)
    
    headers = {
        "Content-Type": "application/json",
        "X-Signature": f"sha256={signature}",
    }
    
    # Exponential backoff retry logic
    delay = 1  # Start with 1 second
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(callback_url, json=payload, headers=headers)
                response.raise_for_status()
                return True
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                # Log failure but don't block
                print(f"Callback failed after {max_retries} attempts: {e}")
                return False
    
    return False


# Import asyncio for sleep
import asyncio


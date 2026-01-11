"""Rate limiting using slowapi and Redis."""
from typing import Optional
from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import redis

from app.core.config import settings

# Initialize Redis client for rate limiting
redis_client = redis.from_url(settings.redis_url, decode_responses=True)

# Initialize limiter
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    default_limits=["1000/hour"],
)


def get_machine_id_from_request(request: Request) -> Optional[str]:
    """Extract machine_id from request body for rate limiting."""
    # This is a fallback; actual rate limiting will use IP + machine_id combo
    # For auth endpoint, we'll use a custom key function
    return None


def get_auth_rate_limit_key(request: Request) -> str:
    """Custom key function for auth endpoint: IP + machine_id."""
    ip = get_remote_address(request)
    # Try to get machine_id from request body (if available)
    # For now, just use IP
    return f"auth:{ip}"


def get_client_rate_limit_key(request: Request) -> str:
    """Custom key function for payment endpoints: client_id from JWT."""
    # This will be set in the dependency after JWT verification
    client_id = getattr(request.state, "client_id", None)
    if client_id:
        return f"payments:{client_id}"
    # Fallback to IP if no client_id
    return f"payments:{get_remote_address(request)}"


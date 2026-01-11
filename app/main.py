"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.rate_limit import limiter
from app.api import health, auth, payments, events, webhooks

# Create FastAPI app
app = FastAPI(
    title="Vending Payment Server",
    description="Bitcoin Lightning payment server for vending machines",
    version="0.1.0",
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware (configure as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/api/v1", tags=["authentication"])
app.include_router(payments.router, prefix="/api/v1", tags=["payments"])
app.include_router(events.router, prefix="/api/v1", tags=["events"])
app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    # Initialize database connection pool, etc.
    pass


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    # Cleanup resources
    pass


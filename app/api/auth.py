"""Authentication endpoints."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from ipaddress import ip_address

from app.core.security import hash_password, verify_password, create_access_token
from app.core.rate_limit import limiter, get_auth_rate_limit_key
from app.db.session import get_db
from app.db.models import Client, ClientAuthEvent
from app.schemas.auth import TokenRequest, TokenResponse

router = APIRouter()


@router.post("/auth/token", response_model=TokenResponse)
@limiter.limit("5/minute")
def create_token(
    request: Request,
    token_request: TokenRequest,
    db: Session = Depends(get_db),
):
    """Authenticate client and issue JWT token."""
    # Get client IP for logging and allowlist check
    client_ip = request.client.host if request.client else None
    
    # Find client by machine_id
    client = db.query(Client).filter(Client.machine_id == token_request.machine_id).first()
    
    if not client:
        # Log failed attempt
        _log_auth_event(
            db,
            client_id=None,
            event_type="LOGIN_FAIL",
            ip=client_ip,
            user_agent=request.headers.get("user-agent"),
            details={"reason": "CLIENT_NOT_FOUND", "machine_id": token_request.machine_id},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    
    # Verify password
    if not verify_password(token_request.password, client.password_hash):
        _log_auth_event(
            db,
            client_id=client.id,
            event_type="LOGIN_FAIL",
            ip=client_ip,
            user_agent=request.headers.get("user-agent"),
            details={"reason": "INVALID_PASSWORD"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    
    # Check if client is active
    if not client.is_active:
        _log_auth_event(
            db,
            client_id=client.id,
            event_type="LOGIN_FAIL",
            ip=client_ip,
            user_agent=request.headers.get("user-agent"),
            details={"reason": "CLIENT_INACTIVE"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client is inactive",
        )
    
    # Check IP allowlist if configured
    if client.allowed_ips:
        if client_ip:
            try:
                ip_obj = ip_address(client_ip)
                allowed = any(ip_obj in network for network in client.allowed_ips)
                if not allowed:
                    _log_auth_event(
                        db,
                        client_id=client.id,
                        event_type="LOGIN_FAIL",
                        ip=client_ip,
                        user_agent=request.headers.get("user-agent"),
                        details={"reason": "IP_NOT_ALLOWED"},
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="IP address not allowed",
                    )
            except ValueError:
                # Invalid IP format
                pass
    
    # Generate JWT token
    token = create_access_token(
        client_id=str(client.id),
        machine_id=client.machine_id,
    )
    
    # Update last_seen_at
    client.last_seen_at = datetime.now(timezone.utc)
    
    # Log successful authentication
    _log_auth_event(
        db,
        client_id=client.id,
        event_type="LOGIN_OK",
        ip=client_ip,
        user_agent=request.headers.get("user-agent"),
        details={"device_info": token_request.device_info},
    )
    
    db.commit()
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=600,  # 10 minutes
    )


def _log_auth_event(
    db: Session,
    client_id,
    event_type: str,
    ip: str = None,
    user_agent: str = None,
    details: dict = None,
):
    """Helper to log authentication events."""
    event = ClientAuthEvent(
        client_id=client_id,
        event_type=event_type,
        ip=ip,
        user_agent=user_agent,
        details=details or {},
    )
    db.add(event)
    db.commit()


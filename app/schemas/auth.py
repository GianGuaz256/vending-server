"""Authentication schemas."""
from typing import Optional
from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    """Request schema for /auth/token."""
    machine_id: str = Field(..., min_length=1, max_length=255, description="Machine identifier")
    password: str = Field(..., min_length=1, description="Client password")
    nonce: Optional[str] = Field(None, max_length=255, description="Optional client nonce")
    device_info: Optional[dict] = Field(None, description="Device metadata")


class TokenResponse(BaseModel):
    """Response schema for /auth/token."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


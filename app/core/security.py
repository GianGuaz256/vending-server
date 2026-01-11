"""Security utilities: password hashing, JWT, HMAC."""
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

# Initialize password hasher with strong parameters
password_hasher = PasswordHasher(
    time_cost=3,  # Number of iterations
    memory_cost=65536,  # 64 MB
    parallelism=4,  # Number of parallel threads
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    try:
        password_hasher.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


def create_access_token(client_id: str, machine_id: str, scope: str = "payments:create payments:read") -> str:
    """Create a JWT access token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    
    payload = {
        "sub": str(client_id),  # Subject (client UUID)
        "mid": machine_id,  # Machine ID
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),  # JWT ID for revocation tracking
        "scope": scope,
    }
    
    private_key = settings.load_jwt_private_key()
    token = jwt.encode(payload, private_key, algorithm=settings.jwt_algorithm)
    return token


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        public_key = settings.load_jwt_public_key()
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": True},
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def verify_hmac_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC signature using constant-time comparison."""
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected_signature, signature)


def generate_hmac_signature(payload: bytes, secret: str) -> str:
    """Generate HMAC signature for payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()


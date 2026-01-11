"""Unit tests for security module."""
import pytest
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_token,
    verify_hmac_signature,
    generate_hmac_signature,
)


class TestPasswordHashing:
    """Test password hashing functionality."""
    
    def test_hash_password(self):
        """Test password hashing."""
        password = "test_password_123"
        hashed = hash_password(password)
        
        assert hashed != password
        assert len(hashed) > 0
        assert hashed.startswith("$argon2id$")
    
    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "test_password_123"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = hash_password(password)
        
        assert verify_password(wrong_password, hashed) is False
    
    def test_different_passwords_different_hashes(self):
        """Test that different passwords produce different hashes."""
        hash1 = hash_password("password1")
        hash2 = hash_password("password2")
        
        assert hash1 != hash2


class TestJWT:
    """Test JWT token functionality."""
    
    def test_create_token(self):
        """Test JWT token creation."""
        client_id = "test-client-id"
        machine_id = "TEST-KIOSK-001"
        
        token = create_access_token(client_id, machine_id)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_verify_token_valid(self):
        """Test token verification with valid token."""
        client_id = "test-client-id"
        machine_id = "TEST-KIOSK-001"
        
        token = create_access_token(client_id, machine_id)
        payload = verify_token(token)
        
        assert payload is not None
        assert payload["sub"] == client_id
        assert payload["mid"] == machine_id
        assert "exp" in payload
        assert "iat" in payload
        assert "jti" in payload
    
    def test_verify_token_invalid(self):
        """Test token verification with invalid token."""
        invalid_token = "invalid.token.here"
        payload = verify_token(invalid_token)
        
        assert payload is None


class TestHMAC:
    """Test HMAC signature functionality."""
    
    def test_generate_signature(self):
        """Test HMAC signature generation."""
        payload = b"test payload"
        secret = "test_secret"
        
        signature = generate_hmac_signature(payload, secret)
        
        assert signature is not None
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex length
    
    def test_verify_signature_valid(self):
        """Test HMAC signature verification with valid signature."""
        payload = b"test payload"
        secret = "test_secret"
        
        signature = generate_hmac_signature(payload, secret)
        is_valid = verify_hmac_signature(payload, signature, secret)
        
        assert is_valid is True
    
    def test_verify_signature_invalid(self):
        """Test HMAC signature verification with invalid signature."""
        payload = b"test payload"
        secret = "test_secret"
        wrong_secret = "wrong_secret"
        
        signature = generate_hmac_signature(payload, secret)
        is_valid = verify_hmac_signature(payload, signature, wrong_secret)
        
        assert is_valid is False
    
    def test_verify_signature_tampered_payload(self):
        """Test HMAC signature verification with tampered payload."""
        payload = b"test payload"
        tampered_payload = b"tampered payload"
        secret = "test_secret"
        
        signature = generate_hmac_signature(payload, secret)
        is_valid = verify_hmac_signature(tampered_payload, signature, secret)
        
        assert is_valid is False


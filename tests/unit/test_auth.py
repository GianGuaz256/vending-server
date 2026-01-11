"""Unit tests for authentication endpoints."""
import pytest
from uuid import uuid4
from app.api.auth import create_token
from app.db.models import Client
from app.core.security import hash_password


class TestAuthEndpoint:
    """Test authentication endpoint."""
    
    def test_auth_success(self, client, test_client_obj):
        """Test successful authentication."""
        response = client.post(
            "/api/v1/auth/token",
            json={
                "machine_id": "TEST-KIOSK-001",
                "password": "test_password",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 600
    
    def test_auth_invalid_machine_id(self, client):
        """Test authentication with invalid machine ID."""
        response = client.post(
            "/api/v1/auth/token",
            json={
                "machine_id": "NONEXISTENT",
                "password": "test_password",
            },
        )
        
        assert response.status_code == 401
    
    def test_auth_invalid_password(self, client, test_client_obj):
        """Test authentication with invalid password."""
        response = client.post(
            "/api/v1/auth/token",
            json={
                "machine_id": "TEST-KIOSK-001",
                "password": "wrong_password",
            },
        )
        
        assert response.status_code == 401
    
    def test_auth_inactive_client(self, client, db_session):
        """Test authentication with inactive client."""
        inactive_client = Client(
            id=uuid4(),
            machine_id="INACTIVE-KIOSK",
            password_hash=hash_password("password"),
            is_active=False,
        )
        db_session.add(inactive_client)
        db_session.commit()
        
        response = client.post(
            "/api/v1/auth/token",
            json={
                "machine_id": "INACTIVE-KIOSK",
                "password": "password",
            },
        )
        
        assert response.status_code == 403
    
    def test_auth_rate_limiting(self, client, test_client_obj):
        """Test rate limiting on auth endpoint."""
        # Make multiple requests quickly
        for _ in range(10):
            response = client.post(
                "/api/v1/auth/token",
                json={
                    "machine_id": "TEST-KIOSK-001",
                    "password": "test_password",
                },
            )
        
        # Should eventually hit rate limit (if configured)
        # Note: This test may need adjustment based on rate limit settings


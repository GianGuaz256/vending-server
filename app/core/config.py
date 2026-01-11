"""Application configuration using Pydantic Settings."""
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(..., description="PostgreSQL connection string")

    # Redis
    redis_url: str = Field(..., description="Redis connection string")

    # JWT Configuration
    jwt_private_key_path: str = Field(default="./jwt_private.pem", description="Path to JWT private key")
    jwt_public_key_path: str = Field(default="./jwt_public.pem", description="Path to JWT public key")
    jwt_algorithm: str = Field(default="RS256", description="JWT signing algorithm")
    jwt_expire_minutes: int = Field(default=10, description="JWT expiration time in minutes")

    # BTCPay Server
    btcpay_base_url: str = Field(..., description="BTCPay Server base URL")
    btcpay_api_key: str = Field(..., description="BTCPay Server API key")
    btcpay_store_id: str = Field(..., description="BTCPay Server store ID")
    btcpay_webhook_secret: str = Field(..., description="BTCPay webhook secret for HMAC verification")

    # Payment Configuration
    payment_monitor_seconds: int = Field(default=120, description="Payment monitoring window in seconds")
    payment_poll_interval_seconds: int = Field(default=5, description="BTCPay polling interval in seconds")

    # API Configuration
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")
    log_level: str = Field(default="INFO", description="Logging level")

    # Rate Limiting
    rate_limit_auth_per_minute: int = Field(default=5, description="Auth endpoint rate limit per minute")
    rate_limit_payments_per_minute: int = Field(default=60, description="Payments endpoint rate limit per minute")

    def load_jwt_private_key(self) -> str:
        """Load JWT private key from file."""
        key_path = Path(self.jwt_private_key_path)
        if not key_path.exists():
            raise FileNotFoundError(f"JWT private key not found at {key_path}")
        return key_path.read_text()

    def load_jwt_public_key(self) -> str:
        """Load JWT public key from file."""
        key_path = Path(self.jwt_public_key_path)
        if not key_path.exists():
            raise FileNotFoundError(f"JWT public key not found at {key_path}")
        return key_path.read_text()


# Global settings instance
settings = Settings()


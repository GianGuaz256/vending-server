"""BTCPay Server Greenfield API client."""
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx

from app.core.config import settings


class BTCPayClient:
    """Client for BTCPay Server Greenfield API."""

    def __init__(self):
        self.base_url = settings.btcpay_base_url.rstrip("/")
        self.api_key = settings.btcpay_api_key
        self.store_id = settings.btcpay_store_id
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"token {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def create_invoice(
        self,
        amount: float,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
        redirect_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a Lightning invoice via BTCPay Server.
        
        Args:
            amount: Payment amount in fiat currency
            currency: Currency code (EUR, USD, etc.)
            metadata: Additional metadata to attach
            redirect_url: Optional redirect URL after payment
            
        Returns:
            BTCPay invoice response dictionary
        """
        # BTCPay Greenfield API expects amount as a string
        # For fiat currencies, we need to specify the amount and currency
        payload = {
            "amount": str(amount),
            "currency": currency,
            "type": "Standard",  # Standard invoice type
            "checkout": {
                "speedPolicy": "MediumSpeed",  # Balance between speed and cost
                "expirationMinutes": 15,  # Invoice expiration
                "monitoringMinutes": 0,  # We handle monitoring ourselves
                "paymentMethods": ["BTC-LightningNetwork"],  # Force Lightning only
                "redirectURL": redirect_url,
            },
            "metadata": metadata or {},
        }

        response = self.client.post(
            f"/api/v1/stores/{self.store_id}/invoices",
            json=payload,
        )
        
        # Enhanced error handling to capture BTCPay error details
        if response.status_code != 200:
            try:
                error_detail = response.json()
                error_msg = f"BTCPay error {response.status_code}: {error_detail}"
            except Exception:
                error_msg = f"BTCPay error {response.status_code}: {response.text}"
            
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"BTCPay create_invoice failed: {error_msg}")
            logger.error(f"Request payload: {payload}")
            
            raise Exception(error_msg)
        
        invoice_data = response.json()
        
        # BTCPay might return the invoice with payment methods already populated
        # If availablePaymentMethods is empty, we may need to wait or fetch again
        return invoice_data

    def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """
        Get invoice details by ID.
        
        Args:
            invoice_id: BTCPay invoice ID
            
        Returns:
            Invoice details dictionary
        """
        response = self.client.get(
            f"/api/v1/stores/{self.store_id}/invoices/{invoice_id}",
        )
        response.raise_for_status()
        return response.json()

    def get_invoice_status(self, invoice_id: str) -> str:
        """
        Get invoice status.
        
        Returns:
            Status string: "New", "Processing", "Settled", "Invalid", "Expired"
        """
        invoice = self.get_invoice(invoice_id)
        return invoice.get("status", "Unknown")

    def get_payment_methods(self, invoice_id: str) -> list[Dict[str, Any]]:
        """
        Get payment methods for an invoice using the payment-methods endpoint.
        
        According to BTCPay Server Greenfield API:
        https://docs.btcpayserver.org/LightningNetwork/
        
        Args:
            invoice_id: BTCPay invoice ID
            
        Returns:
            List of payment method dictionaries
        """
        response = self.client.get(
            f"/api/v1/stores/{self.store_id}/invoices/{invoice_id}/payment-methods",
        )
        response.raise_for_status()
        return response.json()

    def get_lightning_payment_method(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """
        Get Lightning payment method details including BOLT11.
        
        Args:
            invoice_id: BTCPay invoice ID
            
        Returns:
            Payment method dictionary with BOLT11 and other details, or None
        """
        try:
            payment_methods = self.get_payment_methods(invoice_id)
            
            for method in payment_methods:
                # Check paymentMethodId field (BTCPay uses "BTC-LN" for Lightning)
                method_id = method.get("paymentMethodId")
                if method_id in ("BTC-LN", "BTC-LightningNetwork"):
                    return method
            
            return None
        except Exception as e:
            # Log the error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error getting payment methods for invoice {invoice_id}: {e}")
            return None

    def get_bolt11(self, invoice_id: str) -> Optional[str]:
        """
        Extract BOLT11 Lightning invoice string.
        
        According to BTCPay Server Greenfield API documentation:
        https://docs.btcpayserver.org/LightningNetwork/
        
        The BOLT11 invoice is retrieved from the payment-methods endpoint,
        not from the invoice details endpoint.
        
        Args:
            invoice_id: BTCPay invoice ID
            
        Returns:
            BOLT11 string or None
        """
        method = self.get_lightning_payment_method(invoice_id)
        
        if not method:
            return None
        
        # The BOLT11 invoice is in the "destination" field
        # Example: "destination": "lnbc136360n1p55x3ehpp50lpmdf..."
        destination = method.get("destination")
        if destination and isinstance(destination, str) and destination.startswith("lnbc"):
            return destination
        
        # Fallback: Check paymentLink field (may have "lightning:" prefix)
        # Example: "paymentLink": "lightning:lnbc136360n1p55x3ehpp50lpmdf..."
        payment_link = method.get("paymentLink")
        if payment_link and isinstance(payment_link, str):
            # Remove "lightning:" prefix if present
            if payment_link.startswith("lightning:"):
                return payment_link[10:]  # Remove "lightning:" prefix
            elif payment_link.startswith("lnbc"):
                return payment_link
        
        return None

    def get_checkout_link(self, invoice_id: str) -> Optional[str]:
        """
        Get checkout link for invoice.
        
        Args:
            invoice_id: BTCPay invoice ID
            
        Returns:
            Checkout URL or None
        """
        invoice = self.get_invoice(invoice_id)
        return invoice.get("checkoutLink")

    def get_expires_at(self, invoice_id: str) -> Optional[datetime]:
        """
        Get invoice expiration timestamp.
        
        Args:
            invoice_id: BTCPay invoice ID
            
        Returns:
            Expiration datetime or None
        """
        invoice = self.get_invoice(invoice_id)
        expires_str = invoice.get("expirationTime")
        if expires_str:
            try:
                # BTCPay returns ISO 8601 format
                return datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None
        return None

    def is_settled(self, invoice_id: str) -> bool:
        """
        Check if invoice is settled (paid).
        
        Args:
            invoice_id: BTCPay invoice ID
            
        Returns:
            True if invoice is settled
        """
        status = self.get_invoice_status(invoice_id)
        return status == "Settled"

    def close(self):
        """Close HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Global instance (can be reused)
_btcpay_client: Optional[BTCPayClient] = None


def get_btcpay_client() -> BTCPayClient:
    """Get or create BTCPay client instance."""
    global _btcpay_client
    if _btcpay_client is None:
        _btcpay_client = BTCPayClient()
    return _btcpay_client


#!/usr/bin/env python3
"""
Interactive Lightning Payment Client Demo

This script demonstrates the complete payment flow:
1. Health check
2. Authentication
3. Payment invoice creation
4. Real-time status monitoring with QR code display
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from urllib.parse import urljoin

import httpx
import qrcode
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

console = Console()


class PaymentClient:
    """Client for interacting with the Vending Payment Server API."""

    def __init__(self, server_url: str, machine_id: str, password: str):
        self.server_url = server_url.rstrip("/")
        self.machine_id = machine_id
        self.password = password
        self.token: Optional[str] = None
        self.client = httpx.Client(timeout=30.0)

    def _url(self, path: str) -> str:
        """Build full URL from path."""
        return urljoin(self.server_url, path)

    def health_check(self) -> dict:
        """Check server health."""
        response = self.client.get(self._url("/health"))
        response.raise_for_status()
        return response.json()

    def authenticate(self) -> dict:
        """Authenticate and obtain JWT token."""
        response = self.client.post(
            self._url("/api/v1/auth/token"),
            json={
                "machine_id": self.machine_id,
                "password": self.password,
                "device_info": {
                    "client": "client_demo.py",
                    "version": "1.0.0",
                },
            },
        )
        response.raise_for_status()
        data = response.json()
        self.token = data["access_token"]
        return data

    def create_payment(
        self, amount: Decimal, currency: str = "EUR", external_code: Optional[str] = None
    ) -> dict:
        """Create a payment request."""
        if not self.token:
            raise ValueError("Not authenticated. Call authenticate() first.")

        if external_code is None:
            external_code = f"DEMO-{int(time.time())}"

        response = self.client.post(
            self._url("/api/v1/payments"),
            headers={"Authorization": f"Bearer {self.token}"},
            json={
                "payment_method": "BTC_LN",
                "amount": str(amount),
                "currency": currency,
                "external_code": external_code,
                "description": f"Demo payment for {amount} {currency}",
                "metadata": {
                    "demo": True,
                    "client": "client_demo.py",
                },
            },
        )
        response.raise_for_status()
        return response.json()

    def get_payment_status(self, payment_id: str) -> dict:
        """Get payment status."""
        if not self.token:
            raise ValueError("Not authenticated. Call authenticate() first.")

        response = self.client.get(
            self._url(f"/api/v1/payments/{payment_id}"),
            headers={"Authorization": f"Bearer {self.token}"},
        )
        response.raise_for_status()
        return response.json()

    def close(self):
        """Close HTTP client."""
        self.client.close()


def generate_qr_ascii(data: str, border: int = 1) -> str:
    """Generate ASCII art QR code with white background and black squares."""
    qr = qrcode.QRCode(border=border)
    qr.add_data(data)
    qr.make(fit=True)

    # Generate ASCII art using blocks
    # QR codes should have WHITE background and BLACK squares (inverted from terminal default)
    output = []
    matrix = qr.get_matrix()
    for row in matrix:
        line = ""
        for cell in row:
            # Use space for black (QR data), full block for white (background)
            # This creates the correct QR code appearance
            line += "  " if cell else "██"
        output.append(line)

    return "\n".join(output)


def format_time_remaining(expires_at: str) -> tuple[str, str]:
    """
    Format time remaining until expiration.
    Returns (formatted_string, color)
    """
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        remaining = (expiry - now).total_seconds()

        if remaining <= 0:
            return "EXPIRED", "red"
        elif remaining < 30:
            color = "red"
        elif remaining < 60:
            color = "yellow"
        else:
            color = "green"

        minutes = int(remaining // 60)
        seconds = int(remaining % 60)

        if minutes > 0:
            return f"{minutes}m {seconds}s", color
        else:
            return f"{seconds}s", color
    except Exception:
        return "Unknown", "white"


def create_payment_display(payment_data: dict, status_data: Optional[dict] = None) -> Layout:
    """Create rich layout for payment display."""
    layout = Layout()

    # Use latest status data if available
    data = status_data if status_data else payment_data

    # Payment info table
    info_table = Table(show_header=False, box=None, padding=(0, 1))
    info_table.add_column("Key", style="cyan")
    info_table.add_column("Value", style="white")

    info_table.add_row("Payment ID", str(data["payment_id"]))
    info_table.add_row("Status", f"[bold]{data['status']}[/bold]")
    info_table.add_row(
        "Amount",
        f"{data['amount']['amount']} {data['amount']['currency']}",
    )
    info_table.add_row("Order", data["external_code"])

    # Time remaining
    if data.get("invoice", {}).get("expires_at"):
        time_str, time_color = format_time_remaining(data["invoice"]["expires_at"])
        info_table.add_row("Expires in", f"[{time_color}]{time_str}[/{time_color}]")

    # QR Code
    qr_text = ""
    if data.get("lightning_invoice"):
        try:
            qr_text = generate_qr_ascii(data["lightning_invoice"], border=1)
        except Exception as e:
            qr_text = f"QR generation failed: {e}"
    else:
        qr_text = "No Lightning invoice available"

    # BOLT11 invoice - show full invoice
    bolt11_text = data.get("lightning_invoice", "N/A")

    # Checkout link
    checkout_link = data.get("invoice", {}).get("checkout_link", "N/A")
    
    # Provider info
    provider = data.get("invoice", {}).get("provider", "N/A")
    provider_invoice_id = data.get("invoice", {}).get("provider_invoice_id", "N/A")

    # Build invoice details text with full BOLT11
    invoice_details = f"[bold cyan]BOLT11 Lightning Invoice:[/bold cyan]\n"
    invoice_details += f"[yellow]{bolt11_text}[/yellow]\n\n"
    invoice_details += f"[dim]Provider:[/dim] {provider}\n"
    invoice_details += f"[dim]Invoice ID:[/dim] {provider_invoice_id}\n"
    invoice_details += f"[dim]Checkout:[/dim] [blue]{checkout_link}[/blue]"

    # Build layout
    layout.split_column(
        Layout(Panel(info_table, title="💰 Payment Details", border_style="cyan"), size=8),
        Layout(
            Panel(
                qr_text,
                title="⚡ Lightning Invoice QR Code (Scan with your wallet)",
                border_style="yellow",
            ),
            name="qr",
        ),
        Layout(
            Panel(
                invoice_details,
                title="📋 Invoice Details",
                border_style="green",
            ),
            size=9,
        ),
    )

    return layout


def create_status_panel(status: str, message: str = "") -> Panel:
    """Create a status panel with icon."""
    status_icons = {
        "CREATED": "🔨",
        "PENDING": "⏳",
        "PAID": "✅",
        "EXPIRED": "⏰",
        "TIMED_OUT": "⏰",
        "FAILED": "❌",
        "CANCELED": "🚫",
    }

    status_colors = {
        "CREATED": "blue",
        "PENDING": "yellow",
        "PAID": "green",
        "EXPIRED": "red",
        "TIMED_OUT": "red",
        "FAILED": "red",
        "CANCELED": "red",
    }

    icon = status_icons.get(status, "❓")
    color = status_colors.get(status, "white")

    text = Text()
    text.append(f"{icon} {status}", style=f"bold {color}")
    if message:
        text.append(f"\n{message}", style="dim")

    return Panel(text, border_style=color)


async def monitor_payment(client: PaymentClient, payment_id: str, payment_data: dict):
    """Monitor payment status with live updates."""
    console.print("\n")

    # Initial display
    layout = create_payment_display(payment_data)

    # Instructions
    instructions = Panel(
        "[bold yellow]Please pay the invoice using:[/bold yellow]\n\n"
        "1. Scan the QR code with a Lightning wallet\n"
        "2. Copy the BOLT11 invoice and paste it in your wallet\n"
        "3. Open the checkout link in your browser\n\n"
        "[dim]Monitoring payment status every 2 seconds...[/dim]\n"
        "[dim]Press Ctrl+C to stop[/dim]",
        title="📱 How to Pay",
        border_style="blue",
    )

    final_layout = Layout()
    final_layout.split_column(
        Layout(instructions, size=11),
        Layout(layout, name="payment"),
    )

    # Monitor with live display
    status = payment_data["status"]
    poll_count = 0
    max_polls = 60  # 2 minutes at 2-second intervals

    try:
        with Live(final_layout, console=console, refresh_per_second=1) as live:
            while status not in ["PAID", "EXPIRED", "TIMED_OUT", "FAILED", "CANCELED"]:
                if poll_count >= max_polls:
                    console.print(
                        "\n[yellow]⚠️  Monitoring timeout reached (2 minutes)[/yellow]"
                    )
                    break

                await asyncio.sleep(2)
                poll_count += 1

                try:
                    status_data = client.get_payment_status(payment_id)
                    status = status_data["status"]

                    # Update display
                    new_layout = create_payment_display(payment_data, status_data)
                    final_layout["payment"].update(new_layout)

                except Exception as e:
                    console.print(f"[red]Error checking status: {e}[/red]")
                    continue

    except KeyboardInterrupt:
        console.print("\n[yellow]Monitoring stopped by user[/yellow]")
        return

    # Final status
    console.print("\n")
    try:
        final_status = client.get_payment_status(payment_id)
        status = final_status["status"]

        if status == "PAID":
            console.print(
                Panel(
                    "[bold green]✅ PAYMENT SUCCESSFUL![/bold green]\n\n"
                    f"Payment ID: {payment_id}\n"
                    f"Amount: {final_status['amount']['amount']} {final_status['amount']['currency']}\n"
                    f"Finalized at: {final_status.get('finalized_at', 'N/A')}",
                    title="🎉 Success",
                    border_style="green",
                )
            )
        elif status in ["EXPIRED", "TIMED_OUT"]:
            console.print(
                Panel(
                    f"[bold red]⏰ PAYMENT EXPIRED[/bold red]\n\n"
                    f"Status: {status}\n"
                    f"Payment ID: {payment_id}\n"
                    f"Reason: {final_status.get('status_reason', 'Invoice expired')}",
                    title="Timeout",
                    border_style="red",
                )
            )
        elif status == "FAILED":
            console.print(
                Panel(
                    f"[bold red]❌ PAYMENT FAILED[/bold red]\n\n"
                    f"Payment ID: {payment_id}\n"
                    f"Reason: {final_status.get('status_reason', 'Unknown error')}",
                    title="Failed",
                    border_style="red",
                )
            )
        else:
            console.print(
                Panel(
                    f"[yellow]Payment status: {status}[/yellow]\n\n"
                    f"Payment ID: {payment_id}",
                    title="Status",
                    border_style="yellow",
                )
            )

    except Exception as e:
        console.print(f"[red]Error fetching final status: {e}[/red]")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Interactive Lightning Payment Client Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --server-url http://localhost:8000 --machine-id KIOSK-001 --password secret123
  %(prog)s --server-url https://api.example.com --machine-id DEMO-001 --password mypass --amount 2.50
        """,
    )
    parser.add_argument(
        "--server-url",
        required=True,
        help="Server base URL (e.g., http://localhost:8000)",
    )
    parser.add_argument(
        "--machine-id",
        required=True,
        help="Client machine ID",
    )
    parser.add_argument(
        "--password",
        required=True,
        help="Client password",
    )
    parser.add_argument(
        "--amount",
        type=Decimal,
        default=Decimal("1.00"),
        help="Payment amount in EUR (default: 1.00)",
    )

    args = parser.parse_args()

    # Print header
    console.print(
        Panel.fit(
            "[bold cyan]⚡ Lightning Payment Client Demo[/bold cyan]\n"
            "[dim]Bitcoin Lightning Network Payment Flow Demonstration[/dim]",
            border_style="cyan",
        )
    )
    console.print()

    client = PaymentClient(args.server_url, args.machine_id, args.password)

    try:
        # Step 1: Health Check
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("🏥 Checking server health...", total=None)

            try:
                health = client.health_check()
                progress.update(task, completed=True)

                if health.get("status") == "ok":
                    console.print("[green]✓[/green] Server is healthy")
                else:
                    console.print(
                        f"[yellow]⚠[/yellow] Server status: {health.get('status')}"
                    )
                    console.print(f"  Database: {health.get('database')}")

            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]✗[/red] Health check failed: {e}")
                sys.exit(1)

        # Step 2: Authentication
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("🔐 Authenticating...", total=None)

            try:
                auth_data = client.authenticate()
                progress.update(task, completed=True)
                console.print("[green]✓[/green] Authentication successful")
                console.print(f"  Token expires in: {auth_data['expires_in']} seconds")

            except httpx.HTTPStatusError as e:
                progress.update(task, completed=True)
                console.print(f"[red]✗[/red] Authentication failed: {e.response.text}")
                sys.exit(1)
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]✗[/red] Authentication error: {e}")
                sys.exit(1)

        # Step 3: Create Payment
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"💰 Creating payment for {args.amount} EUR...", total=None
            )

            try:
                payment_data = client.create_payment(args.amount)
                progress.update(task, completed=True)
                console.print("[green]✓[/green] Payment created")
                console.print(f"  Payment ID: {payment_data['payment_id']}")
                console.print(f"  Status: {payment_data['status']}")

            except httpx.HTTPStatusError as e:
                progress.update(task, completed=True)
                console.print(f"[red]✗[/red] Payment creation failed: {e.response.text}")
                sys.exit(1)
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[red]✗[/red] Payment error: {e}")
                sys.exit(1)

        # Step 4: Monitor Payment
        await monitor_payment(client, payment_data["payment_id"], payment_data)

    finally:
        client.close()

    console.print("\n[dim]Demo complete![/dim]\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Demo interrupted by user[/yellow]")
        sys.exit(0)


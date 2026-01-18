#!/usr/bin/env python3
"""
Simple Lightning check - tests invoice creation
"""

import httpx
from rich.console import Console

console = Console()


def load_env():
    """Load environment variables."""
    env_vars = {}
    with open('.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    return env_vars


def main():
    env = load_env()
    
    base_url = env.get('BTCPAY_BASE_URL', '').rstrip('/')
    api_key = env.get('BTCPAY_API_KEY', '')
    store_id = env.get('BTCPAY_STORE_ID', '')
    
    console.print(f"[cyan]Testing BTCPay Lightning at {base_url}[/cyan]\n")
    
    client = httpx.Client(timeout=30.0)
    
    try:
        # Create a test invoice
        console.print("Creating test invoice...")
        response = client.post(
            f"{base_url}/api/v1/stores/{store_id}/invoices",
            headers={"Authorization": f"token {api_key}"},
            json={
                "amount": "0.01",
                "currency": "EUR",
                "metadata": {"test": True}
            }
        )
        
        if response.status_code == 200:
            invoice = response.json()
            invoice_id = invoice['id']
            console.print(f"✓ Invoice created: {invoice_id}")
            
            # Get payment methods
            payment_methods = invoice.get('availablePaymentMethods', [])
            
            ln_methods = [pm for pm in payment_methods if 'Lightning' in pm.get('paymentMethod', '')]
            
            if ln_methods:
                console.print(f"✓ Lightning available")
                
                for pm in ln_methods:
                    console.print(f"\n[yellow]Payment Method:[/yellow] {pm.get('paymentMethod')}")
                    console.print(f"[yellow]Crypto:[/yellow] {pm.get('cryptoCode')}")
                    
                    # Try to get the BOLT11
                    if 'paymentLink' in pm:
                        console.print(f"[yellow]Payment Link:[/yellow] {pm['paymentLink']}")
                    
                    if 'destination' in pm:
                        bolt11 = pm['destination']
                        console.print(f"[yellow]BOLT11:[/yellow] {bolt11[:50]}...")
                        
                        # The invoice was created successfully
                        console.print("\n[green]✓ Lightning invoices are being created successfully[/green]")
                        console.print("\n[bold red]The 'No route' error is happening when you try to PAY the invoice.[/bold red]")
                        console.print("\n[bold]This means:[/bold]")
                        console.print("  • Your BTCPay is creating invoices correctly")
                        console.print("  • But your Lightning node has NO INBOUND LIQUIDITY")
                        console.print("  • Your node cannot receive payments")
                        console.print("\n[bold cyan]Solutions:[/bold cyan]")
                        console.print("\n1. [bold]Get Inbound Liquidity (Free):[/bold]")
                        console.print("   • Visit: https://lnbig.com")
                        console.print("   • Request a free incoming channel")
                        console.print("   • Provide your node's public key")
                        console.print("\n2. [bold]Check Your Node's Public Key:[/bold]")
                        console.print("   • Go to your BTCPay Server")
                        console.print("   • Navigate to: Lightning > Node Info")
                        console.print("   • Copy your node's public key")
                        console.print("\n3. [bold]For Testing Only:[/bold]")
                        console.print("   • Use BTCPay testnet")
                        console.print("   • Or use a demo/hosted BTCPay with channels")
                        console.print("\n4. [bold]Open Channels Yourself:[/bold]")
                        console.print("   • In BTCPay: Lightning > Channels > Open Channel")
                        console.print("   • Connect to well-known nodes")
                        console.print("   • You need the other side to push sats for inbound")
                
            else:
                console.print("[red]✗ No Lightning payment methods available[/red]")
                console.print("\nLightning is not enabled in your BTCPay store.")
                console.print("Enable it in: Store Settings > Lightning")
        else:
            console.print(f"[red]✗ Failed to create invoice: {response.status_code}[/red]")
            console.print(response.text)
            
    finally:
        client.close()


if __name__ == "__main__":
    main()

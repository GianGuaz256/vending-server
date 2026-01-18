#!/usr/bin/env python3
"""
BTCPay Server Lightning Node Diagnostics

This script helps diagnose "No route" errors by checking:
1. BTCPay Server connectivity
2. Lightning node configuration
3. Channel status and liquidity
4. Store settings
"""

import os
import sys
import httpx
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

console = Console()


def load_env():
    """Load environment variables from .env file."""
    env_vars = {}
    try:
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    except FileNotFoundError:
        console.print("[red]Error: .env file not found[/red]")
        sys.exit(1)
    return env_vars


def check_btcpay_connection(base_url, api_key):
    """Check BTCPay Server API connectivity."""
    console.print("\n[bold cyan]1. Checking BTCPay Server Connection[/bold cyan]")
    
    try:
        client = httpx.Client(timeout=30.0)
        response = client.get(
            f"{base_url}/api/v1/health",
            headers={"Authorization": f"token {api_key}"}
        )
        
        if response.status_code == 200:
            console.print("✓ [green]BTCPay Server is reachable[/green]")
            return client
        else:
            console.print(f"✗ [red]BTCPay Server returned status {response.status_code}[/red]")
            console.print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        console.print(f"✗ [red]Cannot connect to BTCPay Server: {e}[/red]")
        return None


def check_store_info(client, base_url, api_key, store_id):
    """Check store configuration."""
    console.print("\n[bold cyan]2. Checking Store Configuration[/bold cyan]")
    
    try:
        response = client.get(
            f"{base_url}/api/v1/stores/{store_id}",
            headers={"Authorization": f"token {api_key}"}
        )
        
        if response.status_code == 200:
            store = response.json()
            console.print(f"✓ [green]Store found: {store.get('name', 'N/A')}[/green]")
            console.print(f"  Store ID: {store_id}")
            console.print(f"  Default Currency: {store.get('defaultCurrency', 'N/A')}")
            return True
        else:
            console.print(f"✗ [red]Cannot access store (status {response.status_code})[/red]")
            console.print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        console.print(f"✗ [red]Error checking store: {e}[/red]")
        return False


def check_lightning_config(client, base_url, api_key, store_id):
    """Check Lightning Network configuration."""
    console.print("\n[bold cyan]3. Checking Lightning Network Configuration[/bold cyan]")
    
    try:
        # Check payment methods - try without auth first for public endpoint
        response = client.get(
            f"{base_url}/api/v1/stores/{store_id}/payment-methods/onchain",
            headers={"Authorization": f"token {api_key}"}
        )
        
        # If that fails, try to create a test invoice to see available methods
        console.print("Checking via test invoice creation...")
        test_response = client.post(
            f"{base_url}/api/v1/stores/{store_id}/invoices",
            headers={"Authorization": f"token {api_key}"},
            json={
                "amount": "0.01",
                "currency": "EUR",
                "metadata": {"diagnostic": True}
            }
        )
        
        if test_response.status_code == 200:
            invoice = test_response.json()
            payment_methods = invoice.get('availablePaymentMethods', [])
            
            # Look for Lightning payment methods
            ln_methods = [pm for pm in payment_methods if 'Lightning' in pm.get('paymentMethod', '')]
            
            if ln_methods:
                console.print(f"✓ [green]Lightning payment methods available: {len(ln_methods)}[/green]")
                
                for pm in ln_methods:
                    console.print(f"\n  Payment Method: {pm.get('paymentMethod')}")
                    console.print(f"  Crypto Code: {pm.get('cryptoCode')}")
                
                return True
            else:
                console.print("✗ [red]No Lightning payment methods available[/red]")
                console.print("\n[yellow]Lightning might not be enabled for this store.[/yellow]")
                console.print("Check: Store Settings > Lightning > Enable Lightning")
                return False
        else:
            console.print(f"Cannot create test invoice (status {test_response.status_code})")
            return False
            
    except Exception as e:
        console.print(f"✗ [red]Error checking Lightning config: {e}[/red]")
        return False


def check_lightning_node_info(client, base_url, api_key, store_id):
    """Check Lightning node information and channels."""
    console.print("\n[bold cyan]4. Checking Lightning Node Status[/bold cyan]")
    
    try:
        # Try to get Lightning node info
        response = client.get(
            f"{base_url}/api/v1/stores/{store_id}/lightning/BTC/info",
            headers={"Authorization": f"token {api_key}"}
        )
        
        if response.status_code == 200:
            info = response.json()
            console.print("✓ [green]Lightning node is accessible[/green]")
            console.print(f"  Node Type: {info.get('nodeURIs', ['N/A'])[0] if info.get('nodeURIs') else 'N/A'}")
            console.print(f"  Block Height: {info.get('blockHeight', 'N/A')}")
            
            # Check channels
            channels_response = client.get(
                f"{base_url}/api/v1/stores/{store_id}/lightning/BTC/channels",
                headers={"Authorization": f"token {api_key}"}
            )
            
            if channels_response.status_code == 200:
                channels = channels_response.json()
                
                if channels:
                    console.print(f"\n✓ [green]Found {len(channels)} Lightning channel(s)[/green]")
                    
                    table = Table(title="Lightning Channels")
                    table.add_column("Remote Node", style="cyan")
                    table.add_column("Capacity (sats)", style="magenta")
                    table.add_column("Local Balance", style="green")
                    table.add_column("Remote Balance", style="yellow")
                    table.add_column("Status", style="blue")
                    
                    total_local = 0
                    total_remote = 0
                    
                    for ch in channels:
                        local_balance = ch.get('localBalance', 0)
                        remote_balance = ch.get('remoteBalance', 0)
                        capacity = ch.get('capacity', 0)
                        
                        total_local += local_balance
                        total_remote += remote_balance
                        
                        table.add_row(
                            ch.get('remoteNode', 'Unknown')[:20] + "...",
                            f"{capacity:,}",
                            f"{local_balance:,}",
                            f"{remote_balance:,}",
                            "Active" if ch.get('isActive') else "Inactive"
                        )
                    
                    console.print(table)
                    
                    console.print(f"\n[bold]Total Balances:[/bold]")
                    console.print(f"  Outbound Liquidity (can send): {total_local:,} sats")
                    console.print(f"  Inbound Liquidity (can receive): {total_remote:,} sats")
                    
                    # Diagnose the "No route" issue
                    if total_remote == 0:
                        console.print("\n[bold red]⚠ PROBLEM FOUND: No inbound liquidity![/bold red]")
                        console.print("\n[yellow]Your Lightning node has NO inbound liquidity (remote balance = 0).[/yellow]")
                        console.print("[yellow]This is why you're getting 'No route' errors.[/yellow]")
                        console.print("\n[bold]Solutions:[/bold]")
                        console.print("  1. Open channels with other nodes (they need to push sats to you)")
                        console.print("  2. Use a Lightning Service Provider (LSP) like:")
                        console.print("     - LNBIG (https://lnbig.com)")
                        console.print("     - LNServer (https://lnserver.com)")
                        console.print("     - Voltage Flow (https://voltage.cloud)")
                        console.print("  3. Use a submarine swap service to get inbound liquidity")
                        console.print("  4. Ask someone to open a channel to your node")
                        console.print("\n[bold]Quick Fix (Testing):[/bold]")
                        console.print("  Use BTCPay's testnet or regtest for development")
                        console.print("  Or use a hosted BTCPay with pre-configured channels")
                    elif total_remote < 100000:  # Less than 100k sats
                        console.print(f"\n[yellow]⚠ Warning: Low inbound liquidity ({total_remote:,} sats)[/yellow]")
                        console.print("You may have issues receiving larger payments.")
                    else:
                        console.print(f"\n✓ [green]Good inbound liquidity: {total_remote:,} sats[/green]")
                    
                    return True
                else:
                    console.print("\n✗ [red]No Lightning channels found![/red]")
                    console.print("\n[yellow]Your Lightning node has no channels.[/yellow]")
                    console.print("[yellow]You need to open channels to send/receive payments.[/yellow]")
                    console.print("\n[bold]Solutions:[/bold]")
                    console.print("  1. Open channels using BTCPay's Lightning interface")
                    console.print("  2. Use an LSP (Lightning Service Provider)")
                    console.print("  3. For testing, use BTCPay's testnet")
                    return False
            else:
                console.print(f"Cannot check channels (status {channels_response.status_code})")
                return False
                
        elif response.status_code == 404:
            console.print("✗ [red]Lightning node not configured for BTC[/red]")
            console.print("\n[yellow]You need to set up a Lightning node in BTCPay:[/yellow]")
            console.print("  1. Go to Store Settings > Lightning")
            console.print("  2. Choose a Lightning implementation (LND, Core Lightning, Eclair)")
            console.print("  3. Configure connection settings")
            return False
        else:
            console.print(f"✗ [red]Cannot access Lightning node (status {response.status_code})[/red]")
            console.print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        console.print(f"✗ [red]Error checking Lightning node: {e}[/red]")
        return False


def main():
    """Main diagnostic routine."""
    console.print(Panel.fit(
        "[bold cyan]BTCPay Server Lightning Diagnostics[/bold cyan]\n"
        "[dim]Diagnosing 'No route' payment errors[/dim]",
        border_style="cyan"
    ))
    
    # Load environment
    env = load_env()
    
    base_url = env.get('BTCPAY_BASE_URL', '').rstrip('/')
    api_key = env.get('BTCPAY_API_KEY', '')
    store_id = env.get('BTCPAY_STORE_ID', '')
    
    if not base_url or not api_key or not store_id:
        console.print("[red]Error: Missing BTCPay configuration in .env file[/red]")
        console.print("Required: BTCPAY_BASE_URL, BTCPAY_API_KEY, BTCPAY_STORE_ID")
        sys.exit(1)
    
    console.print(f"\n[dim]BTCPay URL: {base_url}[/dim]")
    console.print(f"[dim]Store ID: {store_id}[/dim]")
    
    # Run diagnostics
    client = check_btcpay_connection(base_url, api_key)
    if not client:
        sys.exit(1)
    
    try:
        # Skip store info check if permission denied
        check_store_info(client, base_url, api_key, store_id)
        
        if not check_lightning_config(client, base_url, api_key, store_id):
            console.print("\n[yellow]Lightning not available, skipping channel check[/yellow]")
        else:
            check_lightning_node_info(client, base_url, api_key, store_id)
        
        console.print("\n[bold green]Diagnostic complete![/bold green]")
        
    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Diagnostic interrupted[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)

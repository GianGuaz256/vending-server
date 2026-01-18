#!/usr/bin/env python3
"""
Check Lightning node channels using public explorers
"""

import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

NODE_PUBKEY = "027cb4e4bf5bd1d12493b419b4843c4abdd8bda4f443392f24cc4ed2185291e3c2"


def check_with_amboss():
    """Check node using Amboss API."""
    console.print("\n[cyan]Checking node on Amboss...[/cyan]")
    
    try:
        client = httpx.Client(timeout=30.0)
        
        # Amboss public API
        response = client.get(
            f"https://api.amboss.space/graphql",
            params={
                "query": f"""
                {{
                  getNode(pubkey: "{NODE_PUBKEY}") {{
                    pubkey
                    alias
                    capacity
                    channel_count
                    graph_info {{
                      channels
                      capacity
                    }}
                  }}
                }}
                """
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and data['data'].get('getNode'):
                node = data['data']['getNode']
                console.print(f"✓ [green]Node found on network[/green]")
                console.print(f"  Alias: {node.get('alias', 'N/A')}")
                console.print(f"  Channels: {node.get('channel_count', 0)}")
                console.print(f"  Total Capacity: {node.get('capacity', 0):,} sats")
                return True
        
        return False
        
    except Exception as e:
        console.print(f"[yellow]Amboss check failed: {e}[/yellow]")
        return False


def check_with_1ml():
    """Check node using 1ML API."""
    console.print("\n[cyan]Checking node on 1ML...[/cyan]")
    
    try:
        client = httpx.Client(timeout=30.0)
        
        response = client.get(
            f"https://1ml.com/node/{NODE_PUBKEY}/json"
        )
        
        if response.status_code == 200:
            node = response.json()
            console.print(f"✓ [green]Node found on 1ML[/green]")
            console.print(f"  Alias: {node.get('alias', 'N/A')}")
            console.print(f"  Channels: {node.get('channelcount', 0)}")
            console.print(f"  Total Capacity: {node.get('capacity', 0):,} sats")
            
            # Check channels
            channels = node.get('channels', [])
            if channels:
                console.print(f"\n[bold]Channel Details:[/bold]")
                
                table = Table()
                table.add_column("Peer", style="cyan")
                table.add_column("Capacity", style="magenta")
                table.add_column("Status", style="green")
                
                for ch in channels[:10]:  # Show first 10
                    peer_alias = ch.get('node2_alias', 'Unknown') if ch.get('node1_pub') == NODE_PUBKEY else ch.get('node1_alias', 'Unknown')
                    capacity = ch.get('capacity', 0)
                    status = "Active" if ch.get('active') else "Inactive"
                    
                    table.add_row(
                        peer_alias[:30],
                        f"{capacity:,}",
                        status
                    )
                
                console.print(table)
                
                # Check for inbound liquidity indicators
                total_capacity = node.get('capacity', 0)
                channel_count = node.get('channelcount', 0)
                
                if channel_count == 0:
                    console.print("\n[bold red]⚠ PROBLEM: No channels found![/bold red]")
                    console.print("Your node has no Lightning channels open.")
                elif total_capacity < 1000000:  # Less than 1M sats
                    console.print(f"\n[yellow]⚠ Warning: Low total capacity ({total_capacity:,} sats)[/yellow]")
                    console.print("You may have limited ability to receive payments.")
                else:
                    console.print(f"\n[green]✓ Node has {channel_count} channels with {total_capacity:,} sats capacity[/green]")
                    console.print("\n[yellow]Note: This shows total capacity, not inbound liquidity.[/yellow]")
                    console.print("[yellow]Inbound liquidity = how much others can send TO you[/yellow]")
                
                return True
            else:
                console.print("\n[red]No channel details available[/red]")
                return False
        else:
            console.print(f"[yellow]1ML returned status {response.status_code}[/yellow]")
            return False
        
    except Exception as e:
        console.print(f"[yellow]1ML check failed: {e}[/yellow]")
        return False


def check_with_mempool():
    """Check node using Mempool.space API."""
    console.print("\n[cyan]Checking node on Mempool.space...[/cyan]")
    
    try:
        client = httpx.Client(timeout=30.0)
        
        response = client.get(
            f"https://mempool.space/api/v1/lightning/nodes/{NODE_PUBKEY}"
        )
        
        if response.status_code == 200:
            node = response.json()
            console.print(f"✓ [green]Node found on Mempool.space[/green]")
            console.print(f"  Alias: {node.get('alias', 'N/A')}")
            console.print(f"  Channels: {node.get('channel_count', 0)}")
            console.print(f"  Total Capacity: {node.get('capacity', 0):,} sats")
            console.print(f"  Active Channels: {node.get('active_channel_count', 0)}")
            
            channel_count = node.get('channel_count', 0)
            active_count = node.get('active_channel_count', 0)
            
            if channel_count == 0:
                console.print("\n[bold red]⚠ PROBLEM: No channels found![/bold red]")
            elif active_count == 0:
                console.print("\n[bold red]⚠ PROBLEM: No active channels![/bold red]")
                console.print("Your channels might be offline or disconnected.")
            else:
                console.print(f"\n[green]✓ Node has {active_count} active channels[/green]")
            
            return True
        else:
            console.print(f"[yellow]Mempool.space returned status {response.status_code}[/yellow]")
            return False
        
    except Exception as e:
        console.print(f"[yellow]Mempool.space check failed: {e}[/yellow]")
        return False


def main():
    """Main check routine."""
    console.print(Panel.fit(
        "[bold cyan]Lightning Node Channel Check[/bold cyan]\n"
        f"[dim]Node: {NODE_PUBKEY[:20]}...[/dim]",
        border_style="cyan"
    ))
    
    # Try multiple explorers
    found = False
    
    found = check_with_mempool() or found
    found = check_with_1ml() or found
    
    if not found:
        console.print("\n[red]Could not find node information on public explorers[/red]")
        console.print("\n[yellow]This could mean:[/yellow]")
        console.print("  1. The node is private/not announced")
        console.print("  2. The node is offline")
        console.print("  3. The node has no public channels")
        console.print("\n[bold]Next steps:[/bold]")
        console.print("  1. Check if your Lightning node is running")
        console.print("  2. In BTCPay: Go to Lightning > Node Info")
        console.print("  3. Check if you have any channels open")
        console.print("  4. If no channels, you need to open some!")
    else:
        console.print("\n[bold cyan]Understanding Inbound Liquidity:[/bold cyan]")
        console.print("\n[yellow]The 'No route' error means you need INBOUND liquidity.[/yellow]")
        console.print("\nInbound liquidity = Remote balance in your channels")
        console.print("This is how much others can send TO you.")
        console.print("\n[bold]To check your actual inbound liquidity:[/bold]")
        console.print("  1. Log in to BTCPay Server")
        console.print("  2. Go to: Lightning > Channels")
        console.print("  3. Look at 'Remote Balance' column")
        console.print("  4. Sum of all remote balances = your inbound liquidity")
        console.print("\n[bold]If remote balance is 0 or very low:[/bold]")
        console.print("  • Request channel from LNBIG: https://lnbig.com")
        console.print("  • Use Amboss Magma: https://amboss.space/magma")
        console.print("  • Ask peers to open channels to you")
        console.print("  • Use submarine swaps to get inbound")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Check interrupted[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()

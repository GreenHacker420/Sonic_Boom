import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from .discovery import scan_speakers, register_master_service, Zeroconf
from .streamer import AudioMaster, AudioSlave

console = Console()

@click.group()
def main():
    """Sonic Boom: Discover and monitor speaker group sync status."""
    pass

@main.command()
@click.option('--group', default='SonicBoomGroup', help='Group name to broadcast.')
@click.option('--name', default='MasterNode', help='Display name of the master.')
def master(group: str, name: str):
    """Start as an audio broadcaster (Master)."""
    devices = AudioMaster.list_devices()
    
    if not devices:
        console.print("[bold red]Error:[/bold red] No audio input devices found.")
        return

    table = Table(title="Available Audio Input Devices")
    table.add_column("Index", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Channels", style="green")

    for d in devices:
        table.add_row(str(d['index']), d['name'], str(d['channels']))
    
    console.print(table)
    
    # Recommendation
    blackhole = next((d for d in devices if 'BlackHole' in d['name']), None)
    recommendation = ""
    if blackhole:
        recommendation = f" (Recommended for System Audio: Index {blackhole['index']})"
    
    device_index = click.prompt(
        f"Select device index to broadcast{recommendation}",
        type=int,
        default=devices[0]['index']
    )

    zc = Zeroconf()
    register_master_service(zc, name, 10000, group)
    
    master_node = AudioMaster(group, device_index=device_index)
    try:
        master_node.start()
    finally:
        zc.close()

@main.command()
@click.option('--timeout', default=5, help='Scanning timeout in seconds.')
def slave(timeout: int):
    """Scan for masters and start as an audio receiver (Slave)."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description="Scanning for Sonic Boom Masters...", total=None)
        speakers = scan_speakers(timeout)

    masters = [s for s in speakers if s.get('service_type') == 'sonic-boom-master']

    multicast_group = '224.3.29.71' # Default
    port = 10000 # Default

    if masters:
        table = Table(title="Available Sonic Boom Masters")
        table.add_column("Index", style="cyan")
        table.add_column("Name", style="magenta")
        table.add_column("Group", style="green")
        table.add_column("Address", style="yellow")

        for i, m in enumerate(masters):
            table.add_row(str(i), m['name'], m['group_id'], f"{m['address']}:{m['port']}")
        
        console.print(table)
        
        choice = click.prompt(
            "Select master index to connect to (or 'm' for manual)",
            default='0'
        )

        if choice != 'm':
            try:
                selected_master = masters[int(choice)]
                # In a real multicast setup, the group IP is usually fixed 
                # or derived from the service info. For now we use the default
                # but we could read it from properties if we stored it there.
                console.print(f"[green]Connecting to {selected_master['name']}...[/green]")
            except (ValueError, IndexError):
                console.print("[red]Invalid selection, using defaults.[/red]")
    else:
        console.print("[yellow]No Sonic Boom Masters found. Proceeding with default multicast group.[/yellow]")

    slave_node = AudioSlave(multicast_group=multicast_group, port=port)
    slave_node.start()

@main.command()
@click.option('--timeout', default=5, help='Scanning timeout in seconds.')
def scan(timeout: int):
    """Scan for local network speaker broadcasters."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description="Scanning for speakers...", total=None)
        speakers = scan_speakers(timeout)

    if not speakers:
        console.print("[yellow]No speaker broadcasters found.[/yellow]")
        return

    # Filter out duplicates (often mDNS returns multiple for the same device)
    unique_speakers = {}
    for s in speakers:
        unique_speakers[s['name']] = s
    speakers = list(unique_speakers.values())

    # Create table
    table = Table(title="Discovered Speaker Broadcasters")
    table.add_column("Name", style="cyan")
    table.add_column("Address", style="magenta")
    table.add_column("Group ID", style="green")
    table.add_column("Status", style="yellow")

    # Group speakers by ID
    groups = {}
    for s in speakers:
        gid = s['group_id']
        if gid not in groups:
            groups[gid] = []
        groups[gid].append(s)

    for gid, members in groups.items():
        is_synced = len(members) > 1 and gid != "None"
        status = "[bold green]Synced[/bold green]" if is_synced else "[bold red]Not Synced[/bold red]"
        
        for i, speaker in enumerate(members):
            table.add_row(
                speaker['name'],
                speaker['address'],
                gid,
                status if i == 0 else "" # Only show status for the group
            )

    console.print()
    if any(len(m) > 1 and g != "None" for g, m in groups.items()):
        console.print("[bold green]Success:[/bold green] Some speakers are currently in sync groups.")
    else:
        console.print("[bold yellow]Note:[/bold yellow] No active sync groups detected.")

if __name__ == "__main__":
    main()

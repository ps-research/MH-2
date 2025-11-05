#!/usr/bin/env python3
"""
Admin Script - Command-line interface to AdminOperations
"""

import sys
from pathlib import Path
import argparse

import redis
from rich.console import Console

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.admin.operations import AdminOperations


console = Console()


def cmd_reset(args, admin):
    """Reset domain or annotator"""
    if args.annotator and args.domain:
        # Reset specific domain
        console.print(f"[yellow]Resetting domain {args.annotator}:{args.domain}...[/yellow]")

        result = admin.reset_domain(args.annotator, args.domain, keep_excel=args.keep_excel)

        if result['success']:
            console.print(f"[green]✓ Reset complete[/green]")

            if result.get('excel_archived'):
                console.print(f"[cyan]Excel archived to:[/cyan] {result['excel_archived']}")
        else:
            console.print(f"[red]✗ Reset failed[/red]")
            sys.exit(1)

    elif args.annotator:
        # Reset all domains for annotator
        console.print(f"[yellow]Resetting all domains for annotator {args.annotator}...[/yellow]")

        result = admin.reset_annotator(args.annotator, keep_excel=args.keep_excel)

        console.print(f"[green]✓ Reset complete for annotator {args.annotator}[/green]")

    else:
        console.print("[red]Error: Must specify --annotator[/red]")
        sys.exit(1)


def cmd_factory_reset(args, admin):
    """Factory reset"""
    if not args.confirm:
        console.print("[red]ERROR: Factory reset requires --confirm flag[/red]")
        console.print("\n[yellow]This operation will:[/yellow]")
        console.print("  • Archive all Excel files")
        console.print("  • Clear all Redis data")
        console.print("  • Stop all workers")
        console.print("  • Cannot be undone!")
        console.print("\n[cyan]Use --confirm to proceed[/cyan]")
        sys.exit(1)

    console.print("[bold red]FACTORY RESET IN PROGRESS[/bold red]")
    console.print("[yellow]This will archive all data and reset the system...[/yellow]\n")

    with console.status("[yellow]Performing factory reset...[/yellow]"):
        result = admin.factory_reset(confirm=True)

    if result['success']:
        console.print("[green]✓ Factory reset complete[/green]")
        console.print(f"[cyan]Archive created:[/cyan] {result.get('archive_path')}")
    else:
        console.print("[red]✗ Factory reset failed[/red]")
        sys.exit(1)


def cmd_export(args, admin):
    """Export state"""
    output_file = args.output or 'data/state_backup.json'

    console.print(f"[yellow]Exporting state to {output_file}...[/yellow]")

    with console.status("[yellow]Exporting...[/yellow]"):
        state_file = admin.export_state(output_file)

    console.print(f"[green]✓ State exported to:[/green] {state_file}")


def cmd_import(args, admin):
    """Import state"""
    if not args.file:
        console.print("[red]Error: Must specify --file[/red]")
        sys.exit(1)

    console.print(f"[yellow]Importing state from {args.file}...[/yellow]")

    with console.status("[yellow]Importing...[/yellow]"):
        result = admin.import_state(args.file, merge=args.merge)

    if result['success']:
        console.print(f"[green]✓ State imported from:[/green] {args.file}")
    else:
        console.print("[red]✗ Import failed[/red]")
        sys.exit(1)


def cmd_archive(args, admin):
    """Archive data"""
    console.print(f"[yellow]Creating archive: {args.name}...[/yellow]")

    with console.status("[yellow]Archiving...[/yellow]"):
        archive_path = admin.archive_data(args.name, compress=args.compress)

    console.print(f"[green]✓ Archive created:[/green] {archive_path}")


def cmd_consolidate(args, admin):
    """Consolidate Excel files"""
    console.print("[yellow]Consolidating Excel files...[/yellow]")

    with console.status("[yellow]Consolidating...[/yellow]"):
        result = admin.consolidate_excel_files()

    if result['success']:
        console.print(f"[green]✓ Consolidation complete[/green]")
        console.print(f"[cyan]Output:[/cyan] {result['output_path']}")
        console.print(f"[cyan]Total rows:[/cyan] {result['total_rows']}")

        # Show worksheet summary
        console.print("\n[bold]Worksheets:[/bold]")
        for worksheet, rows in result.get('worksheets', {}).items():
            console.print(f"  {worksheet}: {rows} rows")
    else:
        console.print("[red]✗ Consolidation failed[/red]")
        sys.exit(1)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Admin Operations for Mental Health Annotation System')

    parser.add_argument('--redis-host', default='localhost', help='Redis host')
    parser.add_argument('--redis-port', type=int, default=6379, help='Redis port')

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Reset command
    reset_parser = subparsers.add_parser('reset', help='Reset domain or annotator')
    reset_parser.add_argument('--annotator', type=int, help='Annotator ID')
    reset_parser.add_argument('--domain', type=str, help='Domain')
    reset_parser.add_argument('--keep-excel', action='store_true', help='Keep Excel files (archive)')

    # Factory reset command
    factory_parser = subparsers.add_parser('factory-reset', help='Factory reset (DESTRUCTIVE)')
    factory_parser.add_argument('--confirm', action='store_true', help='Confirm factory reset')

    # Export command
    export_parser = subparsers.add_parser('export', help='Export state')
    export_parser.add_argument('--output', type=str, help='Output file path')

    # Import command
    import_parser = subparsers.add_parser('import', help='Import state')
    import_parser.add_argument('--file', type=str, required=True, help='Input file path')
    import_parser.add_argument('--merge', action='store_true', help='Merge with existing state')

    # Archive command
    archive_parser = subparsers.add_parser('archive', help='Archive data')
    archive_parser.add_argument('name', type=str, help='Archive name')
    archive_parser.add_argument('--compress', action='store_true', default=True, help='Compress archive')

    # Consolidate command
    consolidate_parser = subparsers.add_parser('consolidate', help='Consolidate Excel files')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Initialize Redis and AdminOperations
    redis_client = redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        decode_responses=True
    )

    admin = AdminOperations(redis_client)

    # Execute command
    try:
        if args.command == 'reset':
            cmd_reset(args, admin)
        elif args.command == 'factory-reset':
            cmd_factory_reset(args, admin)
        elif args.command == 'export':
            cmd_export(args, admin)
        elif args.command == 'import':
            cmd_import(args, admin)
        elif args.command == 'archive':
            cmd_archive(args, admin)
        elif args.command == 'consolidate':
            cmd_consolidate(args, admin)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Start All Workers Script

Launches all enabled workers with:
- Excel file initialization
- Checkpoint synchronization
- Task queue population
- Progress tracking
"""

import os
import sys
from pathlib import Path
import argparse
import time

import redis
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel
from rich.table import Table
from rich import box

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.workers.launcher import WorkerLauncher
from src.storage.excel_manager import ExcelAnnotationManager
from src.core.tasks import populate_task_queues
from src.core.config_loader import ConfigLoader


console = Console()


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description='Start all annotation workers')

    parser.add_argument('--annotator', type=int, help='Start only specific annotator (1-5)')
    parser.add_argument('--domain', type=str, help='Start only specific domain')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be started without starting')
    parser.add_argument('--resync', action='store_true', help='Force re-sync checkpoints from Excel')
    parser.add_argument('--redis-host', default='localhost', help='Redis host')
    parser.add_argument('--redis-port', type=int, default=6379, help='Redis port')

    return parser.parse_args()


def check_prerequisites(redis_client):
    """Check system prerequisites"""
    console.print("[cyan]Checking prerequisites...[/cyan]")

    checks = []

    # Check Redis connection
    try:
        redis_client.ping()
        checks.append(("Redis connection", True, ""))
    except Exception as e:
        checks.append(("Redis connection", False, str(e)))

    # Check data directories
    required_dirs = [
        'data/annotations',
        'data/logs',
        'data/checkpoints',
        'data/malform_logs',
        'data/source'
    ]

    for dir_path in required_dirs:
        exists = os.path.exists(dir_path)
        checks.append((f"Directory: {dir_path}", exists, "" if exists else "Not found"))

        if not exists:
            os.makedirs(dir_path, exist_ok=True)
            console.print(f"[yellow]Created directory:[/yellow] {dir_path}")

    # Check source dataset
    source_file = 'data/source/m_help_dataset.xlsx'
    exists = os.path.exists(source_file)
    checks.append(("Source dataset", exists, "" if exists else "Not found"))

    # Display check results
    table = Table(title="Prerequisites Check", box=box.DOUBLE_EDGE)
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="yellow")
    table.add_column("Note")

    all_passed = True

    for check_name, passed, note in checks:
        status = "[green]✓ PASS[/green]" if passed else "[red]✗ FAIL[/red]"
        table.add_row(check_name, status, note)

        if not passed:
            all_passed = False

    console.print(table)

    if not all_passed:
        console.print("\n[red]Some prerequisites failed. Please fix them before starting workers.[/red]")
        sys.exit(1)

    console.print("\n[green]All prerequisites passed![/green]\n")


def initialize_excel_files(redis_client, workers_to_start, resync=False):
    """Initialize Excel files for workers"""
    console.print("[cyan]Initializing Excel files...[/cyan]")

    excel_mgr = ExcelAnnotationManager('data/annotations', redis_client)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console
    ) as progress:

        task = progress.add_task("Initializing Excel files...", total=len(workers_to_start))

        for annotator_id, domain in workers_to_start:
            # Initialize file
            excel_mgr.initialize_file(annotator_id, domain)

            # Sync checkpoint if resync flag set or file exists
            excel_path = f"data/annotations/annotator_{annotator_id}_{domain}.xlsx"

            if resync or os.path.exists(excel_path):
                synced_count = excel_mgr.sync_checkpoint_from_excel(annotator_id, domain)

                if synced_count > 0:
                    console.print(
                        f"[green]✓[/green] Synced {synced_count} completed samples for {annotator_id}:{domain}"
                    )

            progress.advance(task)

    console.print("[green]Excel initialization complete![/green]\n")


def populate_queues(workers_to_start):
    """Populate task queues"""
    console.print("[cyan]Populating task queues...[/cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:

        task = progress.add_task("Populating queues...", total=1)

        # Populate queues
        results = populate_task_queues()

        progress.advance(task)

    # Display results
    total_queued = results.get('total_queued', 0)
    console.print(f"[green]✓[/green] Queued {total_queued} tasks\n")

    # Show per-worker breakdown
    table = Table(title="Queue Population", box=box.SIMPLE)
    table.add_column("Worker", style="cyan")
    table.add_column("Queued", justify="right")
    table.add_column("Completed", justify="right")
    table.add_column("Total", justify="right")

    by_worker = results.get('by_worker', {})

    for worker_key, worker_info in by_worker.items():
        if worker_info.get('queued', 0) > 0:
            table.add_row(
                worker_key,
                str(worker_info.get('queued', 0)),
                str(worker_info.get('completed', 0)),
                str(worker_info.get('total', 0))
            )

    console.print(table)
    console.print()


def launch_workers(redis_client, workers_to_start, dry_run=False):
    """Launch worker processes"""
    if dry_run:
        console.print("[yellow]DRY RUN: Workers would be started but not actually launching[/yellow]\n")

        table = Table(title="Workers to Start", box=box.DOUBLE_EDGE)
        table.add_column("Annotator", style="cyan")
        table.add_column("Domain", style="yellow")
        table.add_column("Queue Name")

        for annotator_id, domain in workers_to_start:
            queue_name = f"annotator_{annotator_id}_{domain}"
            table.add_row(str(annotator_id), domain, queue_name)

        console.print(table)
        return []

    console.print("[cyan]Launching workers...[/cyan]")

    launcher = WorkerLauncher(redis_client)
    launched_processes = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console
    ) as progress:

        task = progress.add_task("Launching workers...", total=len(workers_to_start))

        for annotator_id, domain in workers_to_start:
            try:
                process = launcher.launch_worker(annotator_id, domain)
                launched_processes.append((annotator_id, domain, process.pid))

                console.print(
                    f"[green]✓[/green] Launched worker {annotator_id}:{domain} (PID: {process.pid})"
                )

                # Small delay between launches
                time.sleep(0.5)

            except Exception as e:
                console.print(f"[red]✗[/red] Failed to launch {annotator_id}:{domain}: {e}")

            progress.advance(task)

    console.print(f"\n[green]Successfully launched {len(launched_processes)} workers![/green]\n")

    # Write PID file
    pid_file = 'data/workers.pid'

    with open(pid_file, 'w') as f:
        for annotator_id, domain, pid in launched_processes:
            f.write(f"{annotator_id}:{domain}:{pid}\n")

    console.print(f"[cyan]PID file written to:[/cyan] {pid_file}\n")

    return launched_processes


def main():
    """Main entry point"""
    args = parse_args()

    # Welcome banner
    console.print(Panel(
        "[bold cyan]Mental Health Annotation System[/bold cyan]\n"
        "Worker Startup Script v4.0",
        title="Start All Workers",
        border_style="green"
    ))

    # Initialize Redis
    redis_client = redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        decode_responses=True
    )

    # Check prerequisites
    check_prerequisites(redis_client)

    # Load worker configuration
    console.print("[cyan]Loading worker configuration...[/cyan]")

    try:
        config_loader = ConfigLoader()
        workers_config = config_loader.load_workers_config()

        # Filter workers based on args
        workers_to_start = []

        for worker in workers_config:
            if not worker.get('enabled', True):
                continue

            annotator_id = worker['annotator_id']
            domain = worker['domain']

            # Apply filters
            if args.annotator and annotator_id != args.annotator:
                continue

            if args.domain and domain != args.domain:
                continue

            workers_to_start.append((annotator_id, domain))

        console.print(f"[green]✓[/green] Loaded configuration for {len(workers_to_start)} workers\n")

    except Exception as e:
        console.print(f"[red]Failed to load configuration:[/red] {e}")
        sys.exit(1)

    if not workers_to_start:
        console.print("[yellow]No workers to start based on filters[/yellow]")
        sys.exit(0)

    # Initialize Excel files
    initialize_excel_files(redis_client, workers_to_start, resync=args.resync)

    # Populate task queues
    if not args.dry_run:
        populate_queues(workers_to_start)

    # Launch workers
    launched_processes = launch_workers(redis_client, workers_to_start, dry_run=args.dry_run)

    # Summary
    if not args.dry_run:
        console.print(Panel(
            f"[green]Successfully started {len(launched_processes)} workers![/green]\n\n"
            f"[cyan]Next steps:[/cyan]\n"
            f"  • Monitor: python scripts/dashboard.py\n"
            f"  • View logs: tail -f data/logs/*.log\n"
            f"  • Stop all: make stop-all",
            title="Startup Complete",
            border_style="green"
        ))


if __name__ == '__main__':
    main()

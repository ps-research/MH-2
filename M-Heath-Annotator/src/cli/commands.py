"""
CLI Commands - Click-based command-line interface

Command groups:
- worker: Worker management (start, stop, pause, resume, status, flush)
- config: Configuration management (edit, validate, reload)
- admin: Admin operations (reset, export, import, archive, consolidate)
- monitor: Monitoring (dashboard, logs, metrics, excel)
- excel: Excel operations (view, verify, consolidate, export)
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

import click
import redis
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.syntax import Syntax
from rich import box

# Import from existing codebase
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.workers.launcher import WorkerLauncher
from src.workers.controller import WorkerController
from src.workers.monitor import WorkerMonitor
from src.api.control import ControlAPI
from src.admin.operations import AdminOperations
from src.cli.excel_viewer import ExcelViewer


# Initialize Redis and console
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
console = Console()


# Helper functions
def get_controller():
    """Get WorkerController instance"""
    return WorkerController(redis_client)


def get_monitor():
    """Get WorkerMonitor instance"""
    return WorkerMonitor(redis_client)


def get_api():
    """Get ControlAPI instance"""
    return ControlAPI(redis_client)


def get_admin():
    """Get AdminOperations instance"""
    return AdminOperations(redis_client)


def get_launcher():
    """Get WorkerLauncher instance"""
    return WorkerLauncher(redis_client)


def format_status_table(statuses: dict) -> Table:
    """Format worker statuses as Rich table"""
    table = Table(title="Worker Status", box=box.DOUBLE_EDGE, show_header=True)

    table.add_column("Worker", style="cyan")
    table.add_column("Status", style="yellow")
    table.add_column("PID", justify="right")
    table.add_column("Uptime", justify="right")
    table.add_column("Tasks", justify="right")
    table.add_column("Excel", justify="right")

    for worker_key, status in statuses.items():
        worker_status = status.get('status', 'unknown')

        # Color code status
        if worker_status == 'running':
            status_text = '[green]Running[/green]'
        elif worker_status == 'paused':
            status_text = '[yellow]Paused[/yellow]'
        elif worker_status == 'stopped':
            status_text = '[red]Stopped[/red]'
        else:
            status_text = '[dim]Unknown[/dim]'

        uptime = status.get('uptime', 0)
        uptime_str = f"{uptime // 3600}h {(uptime % 3600) // 60}m"

        completed = status.get('tasks_processed', 0)
        total = completed + status.get('tasks_remaining', 0)

        excel_file = status.get('excel_file', '')
        excel_name = Path(excel_file).name if excel_file else 'N/A'

        table.add_row(
            worker_key,
            status_text,
            str(status.get('pid', 'N/A')),
            uptime_str,
            f"{completed}/{total}",
            excel_name
        )

    return table


# Main CLI group
@click.group()
@click.version_option(version='4.0.0')
def cli():
    """Mental Health Annotation System - CLI Interface"""
    pass


# ═══════════════════════════════════════════════════════════
# WORKER COMMANDS
# ═══════════════════════════════════════════════════════════

@cli.group()
def worker():
    """Worker management commands"""
    pass


@worker.command()
@click.option('--annotator', '-a', type=int, required=True, help='Annotator ID (1-5)')
@click.option('--domain', '-d', type=str, required=True,
              help='Domain (urgency, therapeutic, intensity, adjunct, modality, redressal)')
def pause(annotator, domain):
    """Pause a specific worker"""
    try:
        controller = get_controller()
        success = controller.pause_worker(annotator, domain)

        if success:
            console.print(f"[green]✓[/green] Paused worker {annotator}:{domain}")
        else:
            console.print(f"[red]✗[/red] Failed to pause worker {annotator}:{domain}")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@worker.command()
@click.option('--annotator', '-a', type=int, required=True, help='Annotator ID (1-5)')
@click.option('--domain', '-d', type=str, required=True, help='Domain')
def resume(annotator, domain):
    """Resume a paused worker"""
    try:
        controller = get_controller()
        success = controller.resume_worker(annotator, domain)

        if success:
            console.print(f"[green]✓[/green] Resumed worker {annotator}:{domain}")
        else:
            console.print(f"[red]✗[/red] Failed to resume worker {annotator}:{domain}")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@worker.command()
@click.option('--annotator', '-a', type=int, help='Annotator ID (1-5)')
@click.option('--domain', '-d', type=str, help='Domain')
@click.option('--all', 'all_workers', is_flag=True, help='Stop all workers')
@click.option('--force', is_flag=True, help='Force kill workers')
def stop(annotator, domain, all_workers, force):
    """Stop workers"""
    try:
        controller = get_controller()

        if all_workers:
            with console.status("[yellow]Stopping all workers...[/yellow]"):
                results = controller.stop_all(force=force)
                stopped = sum(1 for success in results.values() if success)
                console.print(f"[green]✓[/green] Stopped {stopped}/{len(results)} workers")

        elif annotator and domain:
            success = controller.stop_worker(annotator, domain, force=force)

            if success:
                console.print(f"[green]✓[/green] Stopped worker {annotator}:{domain}")
            else:
                console.print(f"[red]✗[/red] Failed to stop worker {annotator}:{domain}")
                sys.exit(1)

        else:
            console.print("[red]Error:[/red] Must specify either --annotator + --domain or --all")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@worker.command()
@click.option('--annotator', '-a', type=int, help='Annotator ID (1-5)')
@click.option('--domain', '-d', type=str, help='Domain')
def flush(annotator, domain):
    """Flush Excel buffer for worker"""
    try:
        controller = get_controller()

        if annotator and domain:
            flushed_rows = controller.flush_excel_buffer(annotator, domain)
            console.print(f"[green]✓[/green] Flushed {flushed_rows} rows to Excel for {annotator}:{domain}")

        else:
            # Flush all
            with console.status("[yellow]Flushing all Excel buffers...[/yellow]"):
                results = controller.flush_all_excel_buffers()
                flushed = sum(1 for success in results.values() if success)
                console.print(f"[green]✓[/green] Flushed {flushed}/{len(results)} buffers")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@worker.command()
@click.option('--annotator', '-a', type=int, help='Annotator ID (1-5)')
@click.option('--domain', '-d', type=str, help='Domain')
def status(annotator, domain):
    """Get worker status"""
    try:
        controller = get_controller()

        if annotator and domain:
            # Single worker status
            status_data = controller.get_worker_status(annotator, domain)

            # Display detailed status
            panel_content = f"""
[cyan]Annotator:[/cyan] {status_data.get('annotator_id')}
[cyan]Domain:[/cyan] {status_data.get('domain')}
[cyan]Status:[/cyan] {status_data.get('status')}
[cyan]PID:[/cyan] {status_data.get('pid')}
[cyan]Uptime:[/cyan] {status_data.get('uptime')}s
[cyan]Tasks Processed:[/cyan] {status_data.get('tasks_processed')}
[cyan]Tasks Remaining:[/cyan] {status_data.get('tasks_remaining')}
[cyan]Excel File:[/cyan] {status_data.get('excel_file')}
"""
            console.print(Panel(panel_content.strip(), title=f"Worker {annotator}:{domain}"))

        else:
            # All workers status
            monitor = get_monitor()
            statuses = monitor.get_all_worker_statuses()

            table = format_status_table(statuses)
            console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════
# CONFIG COMMANDS
# ═══════════════════════════════════════════════════════════

@cli.group()
def config():
    """Configuration management commands"""
    pass


@config.command()
@click.argument('config_type', type=click.Choice(['annotators', 'domains', 'workers', 'settings']))
def edit(config_type):
    """Open config file in default editor"""
    try:
        config_file = f"config/{config_type}.yaml"

        if not os.path.exists(config_file):
            console.print(f"[red]Config file not found:[/red] {config_file}")
            sys.exit(1)

        # Get editor from environment
        editor = os.environ.get('EDITOR', 'nano')

        # Open in editor
        subprocess.run([editor, config_file])

        console.print(f"[green]✓[/green] Config file edited: {config_file}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@config.command()
def validate():
    """Validate configuration files"""
    try:
        # Import config loader
        from src.core.config_loader import ConfigLoader

        loader = ConfigLoader()

        # Validate annotators config
        annotators = loader.load_annotators_config()
        console.print(f"[green]✓[/green] Annotators config valid ({len(annotators)} annotators)")

        # Validate domains config
        domains = loader.load_domains_config()
        console.print(f"[green]✓[/green] Domains config valid ({len(domains)} domains)")

        # Validate workers config
        workers = loader.load_workers_config()
        console.print(f"[green]✓[/green] Workers config valid ({len(workers)} workers)")

        console.print("\n[bold green]All configurations valid![/bold green]")

    except Exception as e:
        console.print(f"[red]Validation failed:[/red] {e}")
        sys.exit(1)


@config.command()
def reload():
    """Reload configuration from files"""
    try:
        # This would trigger a config reload in the system
        console.print("[yellow]Note:[/yellow] Configuration reload requires worker restart")
        console.print("[cyan]Use:[/cyan] annotator-cli worker stop --all && annotator-cli worker start --all")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════
# ADMIN COMMANDS
# ═══════════════════════════════════════════════════════════

@cli.group()
def admin():
    """Administrative operations"""
    pass


@admin.command()
@click.option('--annotator', type=int, help='Annotator ID')
@click.option('--domain', type=str, help='Domain')
@click.option('--keep-excel', is_flag=True, help='Keep Excel files (archive instead of delete)')
@click.confirmation_option(prompt='Are you sure you want to reset?')
def reset(annotator, domain, keep_excel):
    """Reset checkpoints and optionally delete Excel files"""
    try:
        admin_ops = get_admin()

        if annotator and domain:
            # Reset specific domain
            result = admin_ops.reset_domain(annotator, domain, keep_excel=keep_excel)

            if result['success']:
                console.print(f"[green]✓[/green] Reset {annotator}:{domain}")

                if result.get('excel_archived'):
                    console.print(f"[cyan]Excel archived to:[/cyan] {result['excel_archived']}")
            else:
                console.print(f"[red]✗[/red] Failed to reset {annotator}:{domain}")
                sys.exit(1)

        elif annotator:
            # Reset all domains for annotator
            result = admin_ops.reset_annotator(annotator, keep_excel=keep_excel)

            console.print(f"[green]✓[/green] Reset all domains for annotator {annotator}")

        else:
            console.print("[red]Error:[/red] Must specify --annotator and optionally --domain")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@admin.command()
@click.option('--confirm', is_flag=True, help='Confirm factory reset')
def factory_reset(confirm):
    """Factory reset - archives all data and clears Redis (DESTRUCTIVE!)"""
    if not confirm:
        console.print("[red]ERROR:[/red] Factory reset requires --confirm flag")
        console.print("[yellow]This operation will:[/yellow]")
        console.print("  - Archive all Excel files")
        console.print("  - Clear all Redis data")
        console.print("  - Stop all workers")
        console.print("  - Cannot be undone!")
        sys.exit(1)

    try:
        admin_ops = get_admin()

        console.print("[bold red]FACTORY RESET IN PROGRESS[/bold red]")

        with console.status("[yellow]Performing factory reset...[/yellow]"):
            result = admin_ops.factory_reset(confirm=True)

        if result['success']:
            console.print("[green]✓[/green] Factory reset complete")
            console.print(f"[cyan]Archive created:[/cyan] {result.get('archive_path')}")
        else:
            console.print("[red]✗[/red] Factory reset failed")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@admin.command()
@click.argument('archive_name')
@click.option('--compress', is_flag=True, default=True, help='Compress archive (tar.gz)')
def archive(archive_name, compress):
    """Archive current state (Excel files, logs, Redis dump)"""
    try:
        admin_ops = get_admin()

        with console.status(f"[yellow]Creating archive: {archive_name}...[/yellow]"):
            archive_path = admin_ops.archive_data(archive_name, compress=compress)

        console.print(f"[green]✓[/green] Archive created: {archive_path}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@admin.command()
@click.option('--output', type=click.Path(), help='Output file path')
def consolidate(output):
    """Consolidate all Excel files into single file"""
    try:
        admin_ops = get_admin()

        with console.status("[yellow]Consolidating Excel files...[/yellow]"):
            result = admin_ops.consolidate_excel_files()

        if result['success']:
            console.print(f"[green]✓[/green] Consolidation complete")
            console.print(f"[cyan]Output:[/cyan] {result['output_path']}")
            console.print(f"[cyan]Total rows:[/cyan] {result['total_rows']}")

            # Show worksheet summary
            console.print("\n[bold]Worksheets:[/bold]")
            for worksheet, rows in result.get('worksheets', {}).items():
                console.print(f"  {worksheet}: {rows} rows")
        else:
            console.print("[red]✗[/red] Consolidation failed")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════
# EXCEL COMMANDS
# ═══════════════════════════════════════════════════════════

@cli.group()
def excel():
    """Excel file operations"""
    pass


@excel.command()
@click.option('--annotator', '-a', type=int, required=True, help='Annotator ID')
@click.option('--domain', '-d', type=str, required=True, help='Domain')
def view(annotator, domain):
    """View Excel file in terminal"""
    try:
        file_path = f"data/annotations/annotator_{annotator}_{domain}.xlsx"

        if not os.path.exists(file_path):
            console.print(f"[red]Excel file not found:[/red] {file_path}")
            sys.exit(1)

        viewer = ExcelViewer(file_path)
        viewer.run_interactive()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@excel.command()
def verify_all():
    """Verify integrity of all Excel files"""
    try:
        monitor = get_monitor()

        with console.status("[yellow]Verifying Excel files...[/yellow]"):
            integrity = monitor.verify_excel_integrity()

        # Display results in table
        table = Table(title="Excel File Integrity", box=box.DOUBLE_EDGE)
        table.add_column("Worker", style="cyan")
        table.add_column("Status", style="yellow")

        failed_count = 0

        for worker_key, is_valid in integrity.items():
            status = "[green]✓ Valid[/green]" if is_valid else "[red]✗ Corrupted[/red]"
            table.add_row(worker_key, status)

            if not is_valid:
                failed_count += 1

        console.print(table)

        if failed_count > 0:
            console.print(f"\n[red]Warning: {failed_count} file(s) corrupted[/red]")
            sys.exit(1)
        else:
            console.print(f"\n[green]All Excel files valid![/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@excel.command()
@click.option('--annotator', '-a', type=int, required=True, help='Annotator ID')
@click.option('--domain', '-d', type=str, required=True, help='Domain')
@click.option('--output', type=click.Path(), help='Output CSV file path')
def export(annotator, domain, output):
    """Export Excel to CSV"""
    try:
        from src.storage.excel_manager import ExcelAnnotationManager

        excel_mgr = ExcelAnnotationManager('data/annotations', redis_client)

        if not output:
            output = f"data/exports/annotator_{annotator}_{domain}.csv"

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output), exist_ok=True)

        excel_mgr.export_to_csv(annotator, domain, output)

        console.print(f"[green]✓[/green] Exported to: {output}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════
# MONITOR COMMANDS
# ═══════════════════════════════════════════════════════════

@cli.group()
def monitor():
    """Monitoring and metrics"""
    pass


@monitor.command()
@click.option('--refresh-rate', type=int, default=500, help='Update interval (ms)')
@click.option('--excel-sync-interval', type=int, default=2000, help='Excel check interval (ms)')
def dashboard(refresh_rate, excel_sync_interval):
    """Launch Rich TUI dashboard"""
    try:
        from src.cli.dashboard import Dashboard

        dash = Dashboard(
            refresh_rate=refresh_rate,
            excel_sync_interval=excel_sync_interval
        )
        dash.run()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@monitor.command()
def metrics():
    """Show system metrics"""
    try:
        monitor_obj = get_monitor()

        with console.status("[yellow]Collecting metrics...[/yellow]"):
            metrics = monitor_obj.get_system_metrics()

        # Display metrics
        panel_content = f"""
[cyan]CPU:[/cyan] {metrics['cpu_percent']:.1f}%
[cyan]Memory:[/cyan] {metrics['memory']['used_mb']:.0f} MB / {metrics['memory']['total_mb']:.0f} MB ({metrics['memory']['percent']:.1f}%)
[cyan]Disk:[/cyan] {metrics['disk']['used_gb']:.1f} GB / {metrics['disk']['total_gb']:.1f} GB ({metrics['disk']['percent']:.1f}%)
[cyan]Redis Memory:[/cyan] {metrics['redis']['used_memory_mb']:.1f} MB
[cyan]Redis Clients:[/cyan] {metrics['redis']['connected_clients']}
"""
        console.print(Panel(panel_content.strip(), title="System Metrics", style="green"))

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == '__main__':
    cli()

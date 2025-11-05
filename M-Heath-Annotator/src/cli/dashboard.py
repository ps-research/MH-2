"""
Rich TUI Dashboard - Real-time monitoring dashboard

Features:
- Worker grid (5 rows × 6 columns = 30 workers)
- Real-time progress bars
- System metrics
- Recent logs
- Excel file status
- Keyboard shortcuts for control
"""

import os
import sys
import time
import signal
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from collections import deque

import redis
import psutil
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn
from rich.live import Live
from rich.text import Text
from rich import box

# Import from existing codebase
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.workers.controller import WorkerController
from src.workers.monitor import WorkerMonitor
from src.api.control import ControlAPI
from src.storage.excel_manager import ExcelAnnotationManager


class Dashboard:
    """Rich TUI Dashboard for real-time monitoring"""

    # Worker grid layout (5 annotators × 6 domains)
    ANNOTATORS = [1, 2, 3, 4, 5]
    DOMAINS = ['urgency', 'therapeutic', 'intensity', 'adjunct', 'modality', 'redressal']
    DOMAIN_ABBREV = {
        'urgency': 'Urg',
        'therapeutic': 'Ther',
        'intensity': 'Inten',
        'adjunct': 'Adj',
        'modality': 'Mod',
        'redressal': 'Redr'
    }

    def __init__(
        self,
        redis_host: str = 'localhost',
        redis_port: int = 6379,
        refresh_rate: int = 500,
        excel_sync_interval: int = 2000,
        annotations_dir: str = 'data/annotations'
    ):
        """
        Initialize dashboard

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            refresh_rate: Update interval in milliseconds
            excel_sync_interval: Excel file check interval in milliseconds
            annotations_dir: Directory containing Excel annotation files
        """
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
        self.refresh_rate = refresh_rate / 1000  # Convert to seconds
        self.excel_sync_interval = excel_sync_interval / 1000
        self.annotations_dir = annotations_dir

        # Initialize components
        self.controller = WorkerController(self.redis_client)
        self.monitor = WorkerMonitor(self.redis_client)
        self.api = ControlAPI(self.redis_client)
        self.excel_manager = ExcelAnnotationManager(annotations_dir, self.redis_client)

        # State
        self.console = Console()
        self.running = True
        self.logs = deque(maxlen=10)
        self.last_excel_check = 0
        self.selected_worker: Optional[Tuple[int, str]] = None
        self.command_mode = False

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.running = False
        self.console.print("\n[yellow]Shutting down dashboard...[/yellow]")

        # Flush all Excel buffers before exit
        try:
            self.console.print("[cyan]Flushing Excel buffers...[/cyan]")
            results = self.controller.flush_all_excel_buffers()
            flushed = sum(1 for success in results.values() if success)
            self.console.print(f"[green]Flushed {flushed} buffers[/green]")
        except Exception as e:
            self.console.print(f"[red]Error flushing buffers: {e}[/red]")

        sys.exit(0)

    def _get_status_indicator(self, status: str) -> str:
        """Get colored status indicator"""
        indicators = {
            'running': '[green]●[/green] Running',
            'paused': '[yellow]⏸[/yellow] Paused',
            'stopped': '[red]■[/red] Stopped',
            'error': '[orange1]⚠[/orange1] Error',
            'restarting': '[blue]⟳[/blue] Restarting',
            'syncing': '[cyan]💾[/cyan] Syncing',
            'unknown': '[dim]?[/dim] Unknown'
        }
        return indicators.get(status, indicators['unknown'])

    def _get_progress_color(self, percent: float) -> str:
        """Get color based on progress percentage"""
        if percent < 50:
            return 'red'
        elif percent < 80:
            return 'yellow'
        else:
            return 'green'

    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f}MB"

    def _create_worker_cell(self, annotator_id: int, domain: str) -> Panel:
        """Create a single worker cell for the grid"""
        try:
            # Get worker status
            status = self.controller.get_worker_status(annotator_id, domain)

            # Get progress
            completed = status.get('tasks_processed', 0)
            total = completed + status.get('tasks_remaining', 0)
            percent = (completed / total * 100) if total > 0 else 0

            # Get Excel file info
            excel_path = status.get('excel_file', '')
            excel_size = 0
            excel_status = ""

            if excel_path and os.path.exists(excel_path):
                excel_size = os.path.getsize(excel_path)
                excel_status = f"Excel: {self._format_file_size(excel_size)}"
            else:
                excel_status = "Excel: N/A"

            # Get processing rate
            rate = status.get('rate', 0)
            rate_text = f"{rate:.1f}/min" if rate > 0 else "0/min"

            # Build cell content
            lines = []

            # Progress bar
            bar_width = 12
            filled = int(bar_width * percent / 100)
            bar = '█' * filled + '░' * (bar_width - filled)
            color = self._get_progress_color(percent)
            lines.append(f"[{color}]{bar}[/{color}] {percent:.0f}%")

            # Samples count
            lines.append(f"{completed}/{total} samples")

            # Status
            worker_status = status.get('status', 'unknown')
            status_indicator = self._get_status_indicator(worker_status)
            lines.append(f"Status: {status_indicator}")

            # Rate
            lines.append(f"Rate: {rate_text}")

            # Excel size
            lines.append(excel_status)

            content = "\n".join(lines)

            # Create panel
            title = f"A{annotator_id}:{self.DOMAIN_ABBREV[domain]}"
            border_style = "green" if worker_status == 'running' else "dim"

            return Panel(
                content,
                title=title,
                border_style=border_style,
                box=box.ROUNDED,
                padding=(0, 1)
            )

        except Exception as e:
            # Error cell
            return Panel(
                f"[red]Error[/red]\n{str(e)[:20]}",
                title=f"A{annotator_id}:{self.DOMAIN_ABBREV[domain]}",
                border_style="red",
                box=box.ROUNDED
            )

    def _create_worker_grid(self) -> Table:
        """Create the main worker grid"""
        grid = Table.grid(padding=0)

        # Add columns for 6 domains
        for _ in range(6):
            grid.add_column()

        # Add rows for 5 annotators
        for annotator_id in self.ANNOTATORS:
            row_cells = []
            for domain in self.DOMAINS:
                cell = self._create_worker_cell(annotator_id, domain)
                row_cells.append(cell)
            grid.add_row(*row_cells)

        return grid

    def _create_header(self) -> Panel:
        """Create header with system overview"""
        try:
            # Get global status
            status = self.api.get_global_status()
            summary = status.get('summary', {})

            # System metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Build header text
            lines = []

            # Worker summary
            total = summary.get('total_workers', 0)
            running = summary.get('running', 0)
            paused = summary.get('paused', 0)
            stopped = summary.get('stopped', 0)
            healthy = summary.get('healthy', 0)
            unhealthy = summary.get('unhealthy', 0)

            lines.append(f"[bold cyan]Workers:[/bold cyan] {running}/{total} running | "
                        f"{paused} paused | {stopped} stopped | "
                        f"[green]{healthy}[/green] healthy | [red]{unhealthy}[/red] unhealthy")

            # System metrics
            lines.append(f"[bold cyan]System:[/bold cyan] "
                        f"CPU: {cpu_percent:.1f}% | "
                        f"Memory: {memory.percent:.1f}% | "
                        f"Disk: {disk.percent:.1f}%")

            # Progress summary
            checkpoint_summary = status.get('checkpoint_summary', {})
            total_completed = checkpoint_summary.get('total_completed', 0)
            total_samples = checkpoint_summary.get('total_samples', 0)
            overall_progress = (total_completed / total_samples * 100) if total_samples > 0 else 0

            lines.append(f"[bold cyan]Progress:[/bold cyan] "
                        f"{total_completed}/{total_samples} samples ({overall_progress:.1f}%)")

            content = "\n".join(lines)

            return Panel(
                content,
                title="[bold]System Overview[/bold]",
                border_style="bold blue",
                box=box.DOUBLE
            )

        except Exception as e:
            return Panel(
                f"[red]Error fetching status: {e}[/red]",
                title="System Overview",
                border_style="red"
            )

    def _create_logs_panel(self) -> Panel:
        """Create panel with recent logs"""
        if not self.logs:
            log_text = "[dim]No recent logs[/dim]"
        else:
            log_lines = []
            for log in self.logs:
                timestamp = log.get('timestamp', '')
                worker = log.get('worker', '')
                message = log.get('message', '')
                level = log.get('level', 'INFO')

                # Color code by level
                if level == 'ERROR':
                    color = 'red'
                elif level == 'WARNING':
                    color = 'yellow'
                else:
                    color = 'white'

                log_lines.append(f"[{color}][{timestamp}] [{worker}] {message}[/{color}]")

            log_text = "\n".join(log_lines)

        return Panel(
            log_text,
            title="[bold]Recent Logs[/bold]",
            border_style="cyan",
            box=box.ROUNDED
        )

    def _create_excel_status_panel(self) -> Panel:
        """Create panel showing Excel file status"""
        try:
            # Get Excel file sizes
            sizes = self.monitor.get_excel_file_sizes()

            # Build table
            table = Table(show_header=True, box=box.SIMPLE)
            table.add_column("Worker", style="cyan")
            table.add_column("Size", justify="right")
            table.add_column("Modified", justify="right")

            # Show top 10 largest files
            sorted_files = sorted(sizes.items(), key=lambda x: x[1], reverse=True)[:10]

            for worker_key, size in sorted_files:
                parts = worker_key.split('_')
                if len(parts) >= 2:
                    annotator_id = parts[0]
                    domain = parts[1]
                    worker_label = f"A{annotator_id}:{self.DOMAIN_ABBREV.get(domain, domain[:4])}"

                    # Get last modified time
                    file_path = os.path.join(
                        self.annotations_dir,
                        f"annotator_{annotator_id}_{domain}.xlsx"
                    )

                    if os.path.exists(file_path):
                        mtime = os.path.getmtime(file_path)
                        mtime_str = datetime.fromtimestamp(mtime).strftime('%H:%M:%S')
                    else:
                        mtime_str = "N/A"

                    size_str = self._format_file_size(size)
                    table.add_row(worker_label, size_str, mtime_str)

            return Panel(
                table,
                title="[bold]Excel Files (Top 10)[/bold]",
                border_style="magenta",
                box=box.ROUNDED
            )

        except Exception as e:
            return Panel(
                f"[red]Error: {e}[/red]",
                title="Excel Files",
                border_style="red"
            )

    def _create_shortcuts_panel(self) -> Panel:
        """Create panel with keyboard shortcuts"""
        shortcuts_text = """
[cyan]q[/cyan]: Quit | [cyan]p[/cyan]: Pause worker | [cyan]r[/cyan]: Resume worker
[cyan]k[/cyan]: Kill worker | [cyan]f[/cyan]: Flush buffer | [cyan]a[/cyan]: Kill all
[cyan]c[/cyan]: Clear logs | [cyan]e[/cyan]: Excel viewer | [cyan]s[/cyan]: System metrics
[cyan]v[/cyan]: Verify Excel | [cyan]:[/cyan]: Command mode
"""
        return Panel(
            shortcuts_text.strip(),
            title="[bold]Keyboard Shortcuts[/bold]",
            border_style="yellow",
            box=box.ROUNDED
        )

    def _update_logs(self) -> None:
        """Fetch and update recent logs from Redis"""
        try:
            # Fetch last 10 log entries from Redis
            # Key pattern: log:events (sorted set)
            log_entries = self.redis_client.zrevrange('log:events', 0, 9, withscores=True)

            new_logs = []
            for entry, score in log_entries:
                try:
                    # Parse log entry (format: "[timestamp] [worker] message")
                    parts = entry.split('] ', 2)
                    if len(parts) >= 3:
                        timestamp = parts[0].strip('[')
                        worker = parts[1].strip('[')
                        message = parts[2]

                        new_logs.append({
                            'timestamp': timestamp,
                            'worker': worker,
                            'message': message,
                            'level': 'INFO'
                        })
                except Exception:
                    continue

            if new_logs:
                self.logs = deque(new_logs, maxlen=10)

        except Exception as e:
            # Silently fail on log fetch errors
            pass

    def _check_excel_files(self) -> None:
        """Periodically check Excel file integrity"""
        current_time = time.time()

        if current_time - self.last_excel_check >= self.excel_sync_interval:
            try:
                # Verify Excel file integrity
                integrity = self.monitor.verify_excel_integrity()

                # Log any corrupted files
                for worker_key, is_valid in integrity.items():
                    if not is_valid:
                        self._add_log(worker_key, f"Excel file corrupted!", 'ERROR')

                self.last_excel_check = current_time

            except Exception:
                pass

    def _add_log(self, worker: str, message: str, level: str = 'INFO') -> None:
        """Add a log entry"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.logs.append({
            'timestamp': timestamp,
            'worker': worker,
            'message': message,
            'level': level
        })

    def _create_layout(self) -> Layout:
        """Create the dashboard layout"""
        layout = Layout()

        # Split into main sections
        layout.split_column(
            Layout(name="header", size=5),
            Layout(name="body"),
            Layout(name="footer", size=12)
        )

        # Split body into main grid and sidebar
        layout["body"].split_row(
            Layout(name="main", ratio=3),
            Layout(name="sidebar", ratio=1)
        )

        # Split footer
        layout["footer"].split_row(
            Layout(name="logs", ratio=2),
            Layout(name="shortcuts", ratio=1)
        )

        return layout

    def _update_layout(self, layout: Layout) -> None:
        """Update all layout components"""
        try:
            # Update header
            layout["header"].update(self._create_header())

            # Update main grid
            layout["main"].update(self._create_worker_grid())

            # Update sidebar
            layout["sidebar"].update(self._create_excel_status_panel())

            # Update logs
            self._update_logs()
            layout["logs"].update(self._create_logs_panel())

            # Update shortcuts
            layout["shortcuts"].update(self._create_shortcuts_panel())

        except Exception as e:
            # On error, show error panel
            layout["main"].update(Panel(f"[red]Error updating dashboard: {e}[/red]"))

    def run(self) -> None:
        """Run the dashboard with live updates"""
        layout = self._create_layout()

        try:
            with Live(layout, refresh_per_second=1 / self.refresh_rate, screen=True) as live:
                self._add_log("System", "Dashboard started", "INFO")

                while self.running:
                    # Update layout
                    self._update_layout(layout)

                    # Check Excel files periodically
                    self._check_excel_files()

                    # Sleep for refresh interval
                    time.sleep(self.refresh_rate)

        except KeyboardInterrupt:
            self._signal_handler(None, None)
        except Exception as e:
            self.console.print(f"[red]Dashboard error: {e}[/red]")
            raise


def main():
    """Entry point for standalone execution"""
    import argparse

    parser = argparse.ArgumentParser(description='Mental Health Annotation Dashboard')
    parser.add_argument('--host', default='localhost', help='Redis host')
    parser.add_argument('--port', type=int, default=6379, help='Redis port')
    parser.add_argument('--refresh-rate', type=int, default=500,
                       help='Update interval in milliseconds')
    parser.add_argument('--excel-sync-interval', type=int, default=2000,
                       help='Excel file check interval in milliseconds')
    parser.add_argument('--compact', action='store_true',
                       help='Compact view for small terminals')

    args = parser.parse_args()

    try:
        dashboard = Dashboard(
            redis_host=args.host,
            redis_port=args.port,
            refresh_rate=args.refresh_rate,
            excel_sync_interval=args.excel_sync_interval
        )
        dashboard.run()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

"""
Interactive Shell - REPL using prompt_toolkit

Features:
- Command history with persistent storage
- Auto-completion for commands, annotator IDs, domains
- Syntax highlighting
- Multi-line editing
- Context awareness (selected annotator/domain)
"""

import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

import redis
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.panel import Panel

# Import from existing codebase
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.workers.controller import WorkerController
from src.workers.monitor import WorkerMonitor
from src.api.control import ControlAPI
from src.admin.operations import AdminOperations


class AnnotatorCompleter(Completer):
    """Custom completer for annotator commands"""

    COMMANDS = [
        'help', 'exit', 'quit', 'clear',
        'status', 'pause', 'resume', 'stop', 'flush',
        'use', 'context',
        'last-sample', 'malformed-count', 'excel-size',
        'excel-status', 'system', 'workers'
    ]

    ANNOTATOR_IDS = ['1', '2', '3', '4', '5']

    DOMAINS = [
        'urgency', 'therapeutic', 'intensity',
        'adjunct', 'modality', 'redressal'
    ]

    def get_completions(self, document, complete_event):
        """Generate completions"""
        text = document.text_before_cursor
        words = text.split()

        # Command completion
        if len(words) == 0 or (len(words) == 1 and not text.endswith(' ')):
            for cmd in self.COMMANDS:
                if cmd.startswith(text.lower()):
                    yield Completion(cmd, start_position=-len(text))

        # Context-aware completion
        elif len(words) >= 1:
            command = words[0].lower()

            # Commands that take annotator ID
            if command in ['pause', 'resume', 'stop', 'flush', 'use', 'last-sample', 'malformed-count', 'excel-size']:
                if len(words) == 1 or (len(words) == 2 and not text.endswith(' ')):
                    # Complete annotator ID
                    for aid in self.ANNOTATOR_IDS:
                        if aid.startswith(words[-1] if len(words) > 1 else ''):
                            yield Completion(aid, start_position=-len(words[-1]) if len(words) > 1 else 0)

                elif len(words) >= 2:
                    # Complete domain
                    for domain in self.DOMAINS:
                        if domain.startswith(words[-1] if not text.endswith(' ') else ''):
                            yield Completion(
                                domain,
                                start_position=-len(words[-1]) if not text.endswith(' ') else 0
                            )


class InteractiveShell:
    """Interactive shell for Mental Health Annotation System"""

    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379):
        """
        Initialize interactive shell

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
        """
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )

        # Initialize components
        self.controller = WorkerController(self.redis_client)
        self.monitor = WorkerMonitor(self.redis_client)
        self.api = ControlAPI(self.redis_client)
        self.admin = AdminOperations(self.redis_client)

        # State
        self.console = Console()
        self.running = True
        self.context_annotator: Optional[int] = None
        self.context_domain: Optional[str] = None

        # Setup prompt session
        history_file = Path.home() / '.annotator_history'
        self.session = PromptSession(
            history=FileHistory(str(history_file)),
            completer=AnnotatorCompleter(),
            style=Style.from_dict({
                'prompt': 'cyan bold',
            })
        )

    def _get_prompt_text(self) -> HTML:
        """Get prompt text with context"""
        if self.context_annotator and self.context_domain:
            context = f"[A{self.context_annotator}:{self.context_domain}]"
            return HTML(f'<cyan>{context}</cyan> <b>></b> ')
        else:
            return HTML('<cyan>annotator</cyan> <b>></b> ')

    def _parse_command(self, line: str) -> tuple:
        """Parse command line"""
        parts = line.strip().split()

        if not parts:
            return None, []

        command = parts[0].lower()
        args = parts[1:]

        return command, args

    def _execute_command(self, command: str, args: List[str]) -> None:
        """Execute command"""
        try:
            # Help command
            if command in ['help', 'h', '?']:
                self._show_help()

            # Exit commands
            elif command in ['exit', 'quit', 'q']:
                self.running = False
                self.console.print("[yellow]Goodbye![/yellow]")

            # Clear screen
            elif command in ['clear', 'cls']:
                os.system('clear' if os.name != 'nt' else 'cls')

            # Context commands
            elif command == 'use':
                if len(args) >= 2:
                    try:
                        self.context_annotator = int(args[0])
                        self.context_domain = args[1]
                        self.console.print(
                            f"[green]Context set to:[/green] Annotator {self.context_annotator}, Domain {self.context_domain}"
                        )
                    except ValueError:
                        self.console.print("[red]Invalid annotator ID[/red]")
                else:
                    self.console.print("[yellow]Usage:[/yellow] use <annotator_id> <domain>")

            elif command == 'context':
                if self.context_annotator and self.context_domain:
                    self.console.print(
                        f"[cyan]Current context:[/cyan] Annotator {self.context_annotator}, Domain {self.context_domain}"
                    )
                else:
                    self.console.print("[yellow]No context set[/yellow]")

            # Status commands
            elif command in ['status', 'st']:
                self._cmd_status(args)

            # Control commands
            elif command in ['pause', 'pa']:
                self._cmd_pause(args)

            elif command in ['resume', 're']:
                self._cmd_resume(args)

            elif command in ['stop', 'kill']:
                self._cmd_stop(args)

            elif command in ['flush', 'fl']:
                self._cmd_flush(args)

            # Excel commands
            elif command == 'last-sample':
                self._cmd_last_sample(args)

            elif command == 'malformed-count':
                self._cmd_malformed_count(args)

            elif command == 'excel-size':
                self._cmd_excel_size(args)

            elif command == 'excel-status':
                self._cmd_excel_status()

            # System commands
            elif command == 'system':
                self._cmd_system()

            elif command == 'workers':
                self._cmd_workers()

            else:
                self.console.print(f"[red]Unknown command:[/red] {command}")
                self.console.print("[yellow]Type 'help' for available commands[/yellow]")

        except Exception as e:
            self.console.print(f"[red]Error:[/red] {e}")

    def _cmd_status(self, args: List[str]) -> None:
        """Status command"""
        if len(args) >= 2:
            annotator = int(args[0])
            domain = args[1]
        elif self.context_annotator and self.context_domain:
            annotator = self.context_annotator
            domain = self.context_domain
        else:
            self.console.print("[yellow]Usage:[/yellow] status <annotator_id> <domain>")
            self.console.print("[yellow]Or set context with:[/yellow] use <annotator_id> <domain>")
            return

        status = self.controller.get_worker_status(annotator, domain)

        panel_content = f"""
[cyan]Status:[/cyan] {status.get('status')}
[cyan]PID:[/cyan] {status.get('pid')}
[cyan]Uptime:[/cyan] {status.get('uptime')}s
[cyan]Tasks Processed:[/cyan] {status.get('tasks_processed')}
[cyan]Tasks Remaining:[/cyan] {status.get('tasks_remaining')}
[cyan]Excel File:[/cyan] {status.get('excel_file')}
"""
        self.console.print(Panel(panel_content.strip(), title=f"Worker {annotator}:{domain}"))

    def _cmd_pause(self, args: List[str]) -> None:
        """Pause command"""
        if len(args) >= 2:
            annotator = int(args[0])
            domain = args[1]
        elif self.context_annotator and self.context_domain:
            annotator = self.context_annotator
            domain = self.context_domain
        else:
            self.console.print("[yellow]Usage:[/yellow] pause <annotator_id> <domain>")
            return

        success = self.controller.pause_worker(annotator, domain)

        if success:
            self.console.print(f"[green]✓[/green] Paused worker {annotator}:{domain}")
        else:
            self.console.print(f"[red]✗[/red] Failed to pause worker {annotator}:{domain}")

    def _cmd_resume(self, args: List[str]) -> None:
        """Resume command"""
        if len(args) >= 2:
            annotator = int(args[0])
            domain = args[1]
        elif self.context_annotator and self.context_domain:
            annotator = self.context_annotator
            domain = self.context_domain
        else:
            self.console.print("[yellow]Usage:[/yellow] resume <annotator_id> <domain>")
            return

        success = self.controller.resume_worker(annotator, domain)

        if success:
            self.console.print(f"[green]✓[/green] Resumed worker {annotator}:{domain}")
        else:
            self.console.print(f"[red]✗[/red] Failed to resume worker {annotator}:{domain}")

    def _cmd_stop(self, args: List[str]) -> None:
        """Stop command"""
        if len(args) >= 2:
            annotator = int(args[0])
            domain = args[1]
        elif self.context_annotator and self.context_domain:
            annotator = self.context_annotator
            domain = self.context_domain
        else:
            self.console.print("[yellow]Usage:[/yellow] stop <annotator_id> <domain>")
            return

        success = self.controller.stop_worker(annotator, domain, force=False)

        if success:
            self.console.print(f"[green]✓[/green] Stopped worker {annotator}:{domain}")
        else:
            self.console.print(f"[red]✗[/red] Failed to stop worker {annotator}:{domain}")

    def _cmd_flush(self, args: List[str]) -> None:
        """Flush command"""
        if len(args) >= 2:
            annotator = int(args[0])
            domain = args[1]
        elif self.context_annotator and self.context_domain:
            annotator = self.context_annotator
            domain = self.context_domain
        else:
            self.console.print("[yellow]Usage:[/yellow] flush <annotator_id> <domain>")
            return

        flushed_rows = self.controller.flush_excel_buffer(annotator, domain)
        self.console.print(f"[green]✓[/green] Flushed {flushed_rows} rows to Excel")

    def _cmd_last_sample(self, args: List[str]) -> None:
        """Last sample command"""
        if len(args) >= 2:
            annotator = int(args[0])
            domain = args[1]
        elif self.context_annotator and self.context_domain:
            annotator = self.context_annotator
            domain = self.context_domain
        else:
            self.console.print("[yellow]Usage:[/yellow] last-sample <annotator_id> <domain>")
            return

        # Read last row from Excel
        import pandas as pd
        excel_path = f"data/annotations/annotator_{annotator}_{domain}.xlsx"

        if not os.path.exists(excel_path):
            self.console.print(f"[red]Excel file not found:[/red] {excel_path}")
            return

        df = pd.read_excel(excel_path)

        if len(df) > 0:
            last_row = df.iloc[-1]

            panel_content = f"""
[cyan]Sample ID:[/cyan] {last_row.get('Sample_ID', 'N/A')}
[cyan]Label:[/cyan] {last_row.get('Label', 'N/A')}
[cyan]Malformed:[/cyan] {last_row.get('Malformed_Flag', False)}
[cyan]Timestamp:[/cyan] {last_row.get('Timestamp', 'N/A')}
"""
            self.console.print(Panel(panel_content.strip(), title="Last Completed Sample"))
        else:
            self.console.print("[yellow]No samples completed yet[/yellow]")

    def _cmd_malformed_count(self, args: List[str]) -> None:
        """Malformed count command"""
        if len(args) >= 2:
            annotator = int(args[0])
            domain = args[1]
        elif self.context_annotator and self.context_domain:
            annotator = self.context_annotator
            domain = self.context_domain
        else:
            self.console.print("[yellow]Usage:[/yellow] malformed-count <annotator_id> <domain>")
            return

        # Count malformed in Excel
        import pandas as pd
        excel_path = f"data/annotations/annotator_{annotator}_{domain}.xlsx"

        if not os.path.exists(excel_path):
            self.console.print(f"[red]Excel file not found:[/red] {excel_path}")
            return

        df = pd.read_excel(excel_path)

        if 'Malformed_Flag' in df.columns:
            malformed_count = df['Malformed_Flag'].sum()
            total_count = len(df)
            percentage = (malformed_count / total_count * 100) if total_count > 0 else 0

            self.console.print(
                f"[cyan]Malformed:[/cyan] {malformed_count}/{total_count} ({percentage:.1f}%)"
            )
        else:
            self.console.print("[yellow]Malformed_Flag column not found[/yellow]")

    def _cmd_excel_size(self, args: List[str]) -> None:
        """Excel size command"""
        if len(args) >= 2:
            annotator = int(args[0])
            domain = args[1]
        elif self.context_annotator and self.context_domain:
            annotator = self.context_annotator
            domain = self.context_domain
        else:
            self.console.print("[yellow]Usage:[/yellow] excel-size <annotator_id> <domain>")
            return

        excel_path = f"data/annotations/annotator_{annotator}_{domain}.xlsx"

        if not os.path.exists(excel_path):
            self.console.print(f"[red]Excel file not found:[/red] {excel_path}")
            return

        size = os.path.getsize(excel_path)
        size_mb = size / (1024 * 1024)

        self.console.print(f"[cyan]Excel file size:[/cyan] {size_mb:.2f} MB ({size:,} bytes)")

    def _cmd_excel_status(self) -> None:
        """Excel status command"""
        sizes = self.monitor.get_excel_file_sizes()

        from rich.table import Table
        from rich import box

        table = Table(title="Excel File Status", box=box.DOUBLE_EDGE)
        table.add_column("Worker", style="cyan")
        table.add_column("Size", justify="right")

        for worker_key, size in sorted(sizes.items()):
            size_mb = size / (1024 * 1024)
            table.add_row(worker_key, f"{size_mb:.2f} MB")

        self.console.print(table)

    def _cmd_system(self) -> None:
        """System command"""
        metrics = self.monitor.get_system_metrics()

        panel_content = f"""
[cyan]CPU:[/cyan] {metrics['cpu_percent']:.1f}%
[cyan]Memory:[/cyan] {metrics['memory']['percent']:.1f}%
[cyan]Disk:[/cyan] {metrics['disk']['percent']:.1f}%
[cyan]Redis Memory:[/cyan] {metrics['redis']['used_memory_mb']:.1f} MB
"""
        self.console.print(Panel(panel_content.strip(), title="System Metrics"))

    def _cmd_workers(self) -> None:
        """Workers command"""
        statuses = self.monitor.get_all_worker_statuses()

        from rich.table import Table
        from rich import box

        table = Table(title="All Workers", box=box.DOUBLE_EDGE)
        table.add_column("Worker", style="cyan")
        table.add_column("Status", style="yellow")
        table.add_column("Progress", justify="right")

        for worker_key, status in statuses.items():
            worker_status = status.get('status', 'unknown')

            if worker_status == 'running':
                status_text = '[green]Running[/green]'
            elif worker_status == 'paused':
                status_text = '[yellow]Paused[/yellow]'
            else:
                status_text = '[dim]Stopped[/dim]'

            completed = status.get('completed', 0)
            total = status.get('total', 0)
            progress = f"{completed}/{total}"

            table.add_row(worker_key, status_text, progress)

        self.console.print(table)

    def _show_help(self) -> None:
        """Show help"""
        help_text = """
[bold cyan]Mental Health Annotation System - Interactive Shell[/bold cyan]

[yellow]Context Commands:[/yellow]
  use <annotator_id> <domain>  - Set context
  context                      - Show current context

[yellow]Worker Commands:[/yellow]
  status (st)                  - Show worker status
  pause (pa)                   - Pause worker
  resume (re)                  - Resume worker
  stop                         - Stop worker
  flush (fl)                   - Flush Excel buffer

[yellow]Excel Commands:[/yellow]
  last-sample                  - Show last completed sample
  malformed-count              - Count malformed responses
  excel-size                   - Show Excel file size
  excel-status                 - Show all Excel file sizes

[yellow]System Commands:[/yellow]
  system                       - Show system metrics
  workers                      - Show all workers

[yellow]Other:[/yellow]
  help (h, ?)                  - Show this help
  clear (cls)                  - Clear screen
  exit (quit, q)               - Exit shell

[dim]Note: Most commands use context if set, or require <annotator_id> <domain> arguments[/dim]
"""
        self.console.print(Panel(help_text.strip(), title="Help", border_style="cyan"))

    def run(self) -> None:
        """Run interactive shell"""
        # Welcome message
        self.console.print(Panel(
            "[bold cyan]Mental Health Annotation System[/bold cyan]\n"
            "Interactive Shell v4.0\n\n"
            "Type [yellow]help[/yellow] for available commands",
            title="Welcome",
            border_style="green"
        ))

        # Main loop
        while self.running:
            try:
                # Get input
                line = self.session.prompt(self._get_prompt_text())

                # Parse and execute
                command, args = self._parse_command(line)

                if command:
                    self._execute_command(command, args)

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use 'exit' to quit[/yellow]")
            except EOFError:
                break
            except Exception as e:
                self.console.print(f"[red]Error:[/red] {e}")


def main():
    """Entry point for standalone execution"""
    import argparse

    parser = argparse.ArgumentParser(description='Interactive Shell for Mental Health Annotation System')
    parser.add_argument('--host', default='localhost', help='Redis host')
    parser.add_argument('--port', type=int, default=6379, help='Redis port')

    args = parser.parse_args()

    try:
        shell = InteractiveShell(redis_host=args.host, redis_port=args.port)
        shell.run()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

"""
Excel Viewer - Terminal-based Excel file viewer using Rich

Provides interactive viewing of Excel annotation files with:
- Paginated display
- Column filtering
- Search functionality
- Malformed row filtering
- CSV export
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich import box


class ExcelViewer:
    """Terminal-based Excel file viewer with Rich"""

    def __init__(self, file_path: str, rows_per_page: int = 20):
        """
        Initialize Excel viewer

        Args:
            file_path: Path to Excel file
            rows_per_page: Number of rows to display per page
        """
        self.file_path = file_path
        self.rows_per_page = rows_per_page
        self.console = Console()

        # State
        self.df: Optional[pd.DataFrame] = None
        self.filtered_df: Optional[pd.DataFrame] = None
        self.current_page = 0
        self.search_query: Optional[str] = None
        self.malformed_filter_active = False
        self.visible_columns: Optional[List[str]] = None

        # Load file
        self._load_file()

    def _load_file(self) -> None:
        """Load Excel file into DataFrame"""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Excel file not found: {self.file_path}")

        try:
            self.df = pd.read_excel(self.file_path)
            self.filtered_df = self.df.copy()

            # Set default visible columns
            self.visible_columns = list(self.df.columns)

        except Exception as e:
            raise RuntimeError(f"Failed to load Excel file: {e}")

    def reload(self) -> None:
        """Reload Excel file from disk"""
        self._load_file()
        self.current_page = 0
        self.console.print("[green]File reloaded successfully![/green]")

    def get_total_pages(self) -> int:
        """Calculate total number of pages"""
        if self.filtered_df is None or len(self.filtered_df) == 0:
            return 0
        return (len(self.filtered_df) - 1) // self.rows_per_page + 1

    def display_page(self, page_num: Optional[int] = None) -> None:
        """
        Display specific page

        Args:
            page_num: Page number (0-indexed). If None, uses current_page
        """
        if page_num is not None:
            self.current_page = max(0, min(page_num, self.get_total_pages() - 1))

        # Calculate row range
        start_idx = self.current_page * self.rows_per_page
        end_idx = min(start_idx + self.rows_per_page, len(self.filtered_df))

        # Get page data
        page_data = self.filtered_df.iloc[start_idx:end_idx]

        # Create table
        table = Table(
            title=f"Page {self.current_page + 1}/{self.get_total_pages()} ({len(self.filtered_df)} rows)",
            box=box.DOUBLE_EDGE,
            show_header=True,
            header_style="bold cyan"
        )

        # Add columns
        for col in self.visible_columns:
            if col in page_data.columns:
                # Adjust column width based on content
                if col == 'Text':
                    table.add_column(col, max_width=50, overflow="fold")
                elif col in ['Raw_Response']:
                    table.add_column(col, max_width=40, overflow="fold")
                else:
                    table.add_column(col, max_width=30)

        # Add rows
        for idx, row in page_data.iterrows():
            row_values = []
            is_malformed = row.get('Malformed_Flag', False) if 'Malformed_Flag' in row else False

            for col in self.visible_columns:
                if col in row:
                    val = str(row[col]) if pd.notna(row[col]) else ''

                    # Highlight malformed rows
                    if is_malformed and col == 'Label':
                        val = f"[yellow]{val}[/yellow]"
                    elif is_malformed and col == 'Malformed_Flag':
                        val = f"[red]{val}[/red]"

                    row_values.append(val)

            table.add_row(*row_values)

        # Display
        self.console.clear()
        self._display_header()
        self.console.print(table)
        self._display_footer()

    def _display_header(self) -> None:
        """Display header with file info"""
        file_name = Path(self.file_path).name
        file_size = os.path.getsize(self.file_path)
        file_size_mb = file_size / (1024 * 1024)
        total_rows = len(self.df) if self.df is not None else 0
        filtered_rows = len(self.filtered_df) if self.filtered_df is not None else 0

        header_text = f"[bold cyan]{file_name}[/bold cyan]"
        header_text += f" | Size: {file_size_mb:.2f} MB"
        header_text += f" | Total: {total_rows} rows"

        if self.malformed_filter_active:
            header_text += f" | [yellow]Filtered: {filtered_rows} malformed[/yellow]"
        elif self.search_query:
            header_text += f" | [yellow]Search: '{self.search_query}' ({filtered_rows} matches)[/yellow]"

        self.console.print(Panel(header_text, style="bold blue"))

    def _display_footer(self) -> None:
        """Display footer with keyboard shortcuts"""
        shortcuts = [
            "[cyan]j/k[/cyan]: scroll down/up",
            "[cyan]n/p[/cyan]: next/prev page",
            "[cyan]/[/cyan]: search",
            "[cyan]m[/cyan]: toggle malformed",
            "[cyan]l[/cyan]: jump to last",
            "[cyan]r[/cyan]: reload",
            "[cyan]e[/cyan]: export CSV",
            "[cyan]q[/cyan]: quit"
        ]

        footer_text = " | ".join(shortcuts)
        self.console.print(f"\n{footer_text}\n")

    def next_page(self) -> None:
        """Move to next page"""
        if self.current_page < self.get_total_pages() - 1:
            self.current_page += 1
            self.display_page()
        else:
            self.console.print("[yellow]Already at last page[/yellow]")

    def prev_page(self) -> None:
        """Move to previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            self.display_page()
        else:
            self.console.print("[yellow]Already at first page[/yellow]")

    def jump_to_last(self) -> None:
        """Jump to last page"""
        self.current_page = max(0, self.get_total_pages() - 1)
        self.display_page()

    def search(self, query: str) -> List[int]:
        """
        Search for text in Sample_ID or Text columns

        Args:
            query: Search string

        Returns:
            List of matching row indices
        """
        if not query:
            self.filtered_df = self.df.copy()
            self.search_query = None
            self.current_page = 0
            return []

        self.search_query = query

        # Search in Sample_ID and Text columns
        mask = pd.Series([False] * len(self.df))

        if 'Sample_ID' in self.df.columns:
            mask |= self.df['Sample_ID'].astype(str).str.contains(query, case=False, na=False)

        if 'Text' in self.df.columns:
            mask |= self.df['Text'].astype(str).str.contains(query, case=False, na=False)

        self.filtered_df = self.df[mask]
        self.current_page = 0

        matching_indices = self.df.index[mask].tolist()
        return matching_indices

    def filter_malformed(self) -> None:
        """Toggle malformed filter"""
        self.malformed_filter_active = not self.malformed_filter_active

        if self.malformed_filter_active:
            if 'Malformed_Flag' in self.df.columns:
                self.filtered_df = self.df[self.df['Malformed_Flag'] == True]
            else:
                self.console.print("[yellow]Warning: Malformed_Flag column not found[/yellow]")
                self.filtered_df = self.df.copy()
        else:
            self.filtered_df = self.df.copy()

        self.current_page = 0

    def export_filtered(self, output_path: str) -> None:
        """
        Export filtered data to CSV

        Args:
            output_path: Output CSV file path
        """
        try:
            self.filtered_df.to_csv(output_path, index=False)
            self.console.print(f"[green]Exported {len(self.filtered_df)} rows to {output_path}[/green]")
        except Exception as e:
            self.console.print(f"[red]Export failed: {e}[/red]")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the Excel file"""
        if self.df is None:
            return {}

        stats = {
            'total_rows': len(self.df),
            'columns': list(self.df.columns),
            'file_size_mb': os.path.getsize(self.file_path) / (1024 * 1024)
        }

        # Count malformed if column exists
        if 'Malformed_Flag' in self.df.columns:
            stats['malformed_count'] = self.df['Malformed_Flag'].sum()
            stats['malformed_rate'] = (stats['malformed_count'] / len(self.df)) * 100

        # Count by label if column exists
        if 'Label' in self.df.columns:
            stats['label_distribution'] = self.df['Label'].value_counts().to_dict()

        return stats

    def display_stats(self) -> None:
        """Display statistics panel"""
        stats = self.get_stats()

        if not stats:
            self.console.print("[red]No statistics available[/red]")
            return

        lines = []
        lines.append(f"Total Rows: {stats['total_rows']}")
        lines.append(f"File Size: {stats['file_size_mb']:.2f} MB")
        lines.append(f"Columns: {len(stats['columns'])}")

        if 'malformed_count' in stats:
            lines.append(f"Malformed: {stats['malformed_count']} ({stats['malformed_rate']:.1f}%)")

        if 'label_distribution' in stats:
            lines.append("\nLabel Distribution:")
            for label, count in stats['label_distribution'].items():
                lines.append(f"  {label}: {count}")

        stats_text = "\n".join(lines)
        self.console.print(Panel(stats_text, title="Statistics", style="green"))

    def run_interactive(self) -> None:
        """Run interactive viewer with keyboard controls"""
        self.display_page()

        try:
            while True:
                # Get user input
                command = self.console.input("\n[cyan]Command[/cyan] ([yellow]h[/yellow] for help): ").strip().lower()

                if command in ['q', 'quit', 'exit']:
                    break
                elif command in ['n', 'next']:
                    self.next_page()
                elif command in ['p', 'prev', 'previous']:
                    self.prev_page()
                elif command in ['j', 'down']:
                    self.next_page()
                elif command in ['k', 'up']:
                    self.prev_page()
                elif command in ['l', 'last']:
                    self.jump_to_last()
                elif command in ['f', 'first']:
                    self.current_page = 0
                    self.display_page()
                elif command in ['r', 'reload']:
                    self.reload()
                    self.display_page()
                elif command in ['m', 'malformed']:
                    self.filter_malformed()
                    self.display_page()
                elif command in ['s', 'stats']:
                    self.display_stats()
                elif command.startswith('/'):
                    # Search mode
                    query = command[1:].strip()
                    matches = self.search(query)
                    self.display_page()
                    self.console.print(f"[green]Found {len(matches)} matches[/green]")
                elif command == 'e':
                    # Export mode
                    output_path = self.console.input("Export to (CSV path): ").strip()
                    if output_path:
                        self.export_filtered(output_path)
                elif command == 'c':
                    # Clear filters
                    self.search_query = None
                    self.malformed_filter_active = False
                    self.filtered_df = self.df.copy()
                    self.current_page = 0
                    self.display_page()
                    self.console.print("[green]Filters cleared[/green]")
                elif command in ['h', 'help', '?']:
                    self._display_help()
                else:
                    self.console.print(f"[yellow]Unknown command: {command}[/yellow]")

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Exiting...[/yellow]")

    def _display_help(self) -> None:
        """Display help panel"""
        help_text = """
[cyan]Navigation:[/cyan]
  n, next       - Next page
  p, prev       - Previous page
  j, down       - Scroll down (next page)
  k, up         - Scroll up (previous page)
  l, last       - Jump to last page
  f, first      - Jump to first page

[cyan]Filtering:[/cyan]
  /query        - Search for text
  m, malformed  - Toggle malformed filter
  c             - Clear all filters

[cyan]Actions:[/cyan]
  r, reload     - Reload file from disk
  s, stats      - Show statistics
  e             - Export filtered data to CSV

[cyan]Other:[/cyan]
  h, help       - Show this help
  q, quit       - Exit viewer
"""
        self.console.print(Panel(help_text, title="Help", style="cyan"))


def main():
    """Entry point for standalone execution"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python excel_viewer.py <excel_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    try:
        viewer = ExcelViewer(file_path)
        viewer.run_interactive()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

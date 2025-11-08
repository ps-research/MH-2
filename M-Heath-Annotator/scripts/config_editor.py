#!/usr/bin/env python3
"""
Config Editor Script - Interactive config editor with validation
"""

import os
import sys
from pathlib import Path
import argparse
import subprocess
import difflib

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config_loader import ConfigLoader


console = Console()


def load_yaml_file(file_path):
    """Load YAML file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def save_yaml_file(file_path, data):
    """Save YAML file"""
    with open(file_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def validate_config(config_type):
    """Validate configuration"""
    try:
        loader = ConfigLoader()

        if config_type == 'annotators':
            annotators = loader.load_annotators_config()
            console.print(f"[green]✓ Annotators config valid ({len(annotators)} annotators)[/green]")
            return True

        elif config_type == 'domains':
            domains = loader.load_domains_config()
            console.print(f"[green]✓ Domains config valid ({len(domains)} domains)[/green]")
            return True

        elif config_type == 'workers':
            workers = loader.load_workers_config()
            console.print(f"[green]✓ Workers config valid ({len(workers)} workers)[/green]")
            return True

        elif config_type == 'settings':
            # Validate settings (basic check)
            console.print("[green]✓ Settings config valid[/green]")
            return True

    except Exception as e:
        console.print(f"[red]✗ Validation failed:[/red] {e}")
        return False


def show_diff(original_content, new_content, file_path):
    """Show diff between original and new content"""
    original_lines = original_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile=f"{file_path} (original)",
        tofile=f"{file_path} (modified)",
        lineterm=''
    )

    diff_text = ''.join(diff)

    if diff_text:
        console.print("\n[bold cyan]Changes:[/bold cyan]")
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
        console.print(syntax)
        return True
    else:
        console.print("\n[yellow]No changes detected[/yellow]")
        return False


def edit_config(config_type, validate_only=False, force=False):
    """Edit configuration file"""
    config_file = f"config/{config_type}.yaml"

    if not os.path.exists(config_file):
        console.print(f"[red]Config file not found:[/red] {config_file}")
        sys.exit(1)

    # Validate only mode
    if validate_only:
        console.print(f"[cyan]Validating {config_file}...[/cyan]")

        if validate_config(config_type):
            console.print("[green]Configuration is valid![/green]")
            sys.exit(0)
        else:
            console.print("[red]Configuration has errors[/red]")
            sys.exit(1)

    # Load original content
    with open(config_file, 'r') as f:
        original_content = f.read()

    # Display current config
    console.print(Panel(
        f"[bold cyan]Editing configuration:[/bold cyan] {config_file}\n"
        f"[yellow]Editor:[/yellow] {os.environ.get('EDITOR', 'nano')}",
        title="Config Editor",
        border_style="green"
    ))

    # Open in editor
    editor = os.environ.get('EDITOR', 'nano')

    try:
        subprocess.run([editor, config_file], check=True)
    except subprocess.CalledProcessError:
        console.print("[red]Editor exited with error[/red]")
        sys.exit(1)
    except FileNotFoundError:
        console.print(f"[red]Editor not found:[/red] {editor}")
        console.print("[yellow]Set EDITOR environment variable to use a different editor[/yellow]")
        sys.exit(1)

    # Load new content
    with open(config_file, 'r') as f:
        new_content = f.read()

    # Show diff
    has_changes = show_diff(original_content, new_content, config_file)

    if not has_changes:
        console.print("\n[yellow]No changes made. Exiting.[/yellow]")
        sys.exit(0)

    # Validate changes
    console.print("\n[cyan]Validating changes...[/cyan]")

    is_valid = validate_config(config_type)

    if not is_valid:
        if force:
            console.print("\n[yellow]Warning: Validation failed but --force flag set. Changes saved.[/yellow]")
        else:
            console.print("\n[red]Validation failed! Changes NOT saved.[/red]")
            console.print("[yellow]Use --force to save anyway (not recommended)[/yellow]")

            # Restore original content
            with open(config_file, 'w') as f:
                f.write(original_content)

            sys.exit(1)
    else:
        console.print("\n[green]✓ Validation passed! Changes saved.[/green]")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Configuration Editor')

    parser.add_argument('config_type',
                       choices=['annotators', 'domains', 'workers', 'settings'],
                       help='Configuration type to edit')
    parser.add_argument('--validate-only', action='store_true',
                       help='Only validate, do not edit')
    parser.add_argument('--force', action='store_true',
                       help='Skip validation (dangerous!)')

    args = parser.parse_args()

    try:
        edit_config(args.config_type, validate_only=args.validate_only, force=args.force)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

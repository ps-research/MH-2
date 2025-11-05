#!/usr/bin/env python3
"""
Excel Viewer Script - Standalone Excel file viewer
"""

import sys
from pathlib import Path
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cli.excel_viewer import ExcelViewer


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Excel File Viewer for Annotation Files')

    parser.add_argument('--file', type=str, help='Path to Excel file')
    parser.add_argument('--annotator', '-a', type=int, help='Annotator ID (1-5)')
    parser.add_argument('--domain', '-d', type=str, help='Domain name')
    parser.add_argument('--filter-malformed', action='store_true',
                       help='Show only malformed rows')
    parser.add_argument('--export-csv', type=str,
                       help='Export to CSV and exit')

    args = parser.parse_args()

    # Determine file path
    if args.file:
        file_path = args.file
    elif args.annotator and args.domain:
        file_path = f"data/annotations/annotator_{args.annotator}_{args.domain}.xlsx"
    else:
        print("Error: Must specify either --file or --annotator + --domain")
        parser.print_help()
        sys.exit(1)

    try:
        # Initialize viewer
        viewer = ExcelViewer(file_path)

        # Apply malformed filter if requested
        if args.filter_malformed:
            viewer.filter_malformed()

        # Export mode
        if args.export_csv:
            viewer.export_filtered(args.export_csv)
            print(f"Exported to: {args.export_csv}")
            sys.exit(0)

        # Interactive mode
        viewer.run_interactive()

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

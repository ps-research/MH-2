#!/usr/bin/env python3
"""
Dashboard Script - Entry point for Rich TUI dashboard
"""

import sys
from pathlib import Path
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cli.dashboard import Dashboard


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Mental Health Annotation Dashboard')

    parser.add_argument('--host', default='localhost', help='Redis host')
    parser.add_argument('--port', type=int, default=6379, help='Redis port')
    parser.add_argument('--refresh-rate', type=int, default=500,
                       help='Update interval in milliseconds (default: 500)')
    parser.add_argument('--excel-sync-interval', type=int, default=2000,
                       help='Excel file check interval in milliseconds (default: 2000)')
    parser.add_argument('--compact', action='store_true',
                       help='Compact view for small terminals')
    parser.add_argument('--annotations-dir', default='data/annotations',
                       help='Directory containing Excel annotation files')

    args = parser.parse_args()

    try:
        dashboard = Dashboard(
            redis_host=args.host,
            redis_port=args.port,
            refresh_rate=args.refresh_rate,
            excel_sync_interval=args.excel_sync_interval,
            annotations_dir=args.annotations_dir
        )

        print("Starting dashboard... (Press Ctrl+C to exit)")
        dashboard.run()

    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

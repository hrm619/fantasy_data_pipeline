#!/usr/bin/env python3
"""
Fantasy Football Rankings CLI - Main Entry Point

Central command-line interface for fantasy football rankings pipeline.
"""

import sys
import argparse
from fantasy_pipeline.cli.rankings import main as rankings_main


def main():
    """Main CLI entry point with subcommands."""
    parser = argparse.ArgumentParser(
        description='Fantasy Football Rankings Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s rankings --league-type redraft
  %(prog)s rankings --league-type weekly --week 7
  %(prog)s rankings --league-type ros
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Rankings subcommand
    rankings_parser = subparsers.add_parser(
        'rankings',
        help='Process fantasy football rankings'
    )
    rankings_parser.add_argument(
        '--league-type',
        choices=['redraft', 'bestball', 'weekly', 'ros'],
        default='redraft',
        help='Type of league to process (default: redraft)'
    )
    rankings_parser.add_argument(
        '--week',
        type=int,
        help='Week number for weekly rankings (required when league-type is weekly)'
    )
    rankings_parser.add_argument(
        '--data-path',
        help='Path to update directory containing ranking files'
    )
    rankings_parser.add_argument(
        '--player-key-path',
        help='Path to player key dictionary JSON file'
    )
    rankings_parser.add_argument(
        '--base-data-dir',
        help='Base directory containing latest, update, archive folders'
    )
    rankings_parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress verbose output'
    )

    args = parser.parse_args()

    # If no command specified, show help
    if not args.command:
        parser.print_help()
        return 0

    # Route to appropriate command
    if args.command == 'rankings':
        return rankings_main(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())

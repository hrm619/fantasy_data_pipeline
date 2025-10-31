#!/usr/bin/env python3
"""
Fantasy Football Rankings CLI Command

Process fantasy football rankings from multiple sources.
"""

import sys
from fantasy_pipeline import RankingsProcessor


def main(args=None):
    """
    Process fantasy football rankings.

    Args:
        args: Parsed arguments from argparse (if called from main.py)
              If None, will parse sys.argv directly
    """
    # If called standalone, parse arguments
    if args is None:
        import argparse
        parser = argparse.ArgumentParser(description='Process fantasy football rankings')
        parser.add_argument(
            '--league-type',
            choices=['redraft', 'bestball', 'weekly', 'ros'],
            default='redraft',
            help='Type of league to process (default: redraft)'
        )
        parser.add_argument(
            '--week',
            type=int,
            help='Week number for weekly/ROS rankings (required when league-type is weekly or ros)'
        )
        parser.add_argument(
            '--data-path',
            help='Path to update directory containing ranking files'
        )
        parser.add_argument(
            '--player-key-path',
            help='Path to player key dictionary JSON file'
        )
        parser.add_argument(
            '--base-data-dir',
            help='Base directory containing latest, update, archive folders'
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Suppress verbose output'
        )
        args = parser.parse_args()

    # Validate week parameter for weekly and ROS league types
    if args.league_type in ['weekly', 'ros'] and args.week is None:
        print(f"Error: --week parameter is required when --league-type is '{args.league_type}'")
        return 1

    try:
        processor = RankingsProcessor(args.league_type, args.week)

        output_file = processor.process_rankings(
            data_path=args.data_path,
            player_key_path=args.player_key_path,
            base_data_dir=args.base_data_dir,
            week=args.week,
            verbose=not args.quiet
        )

        print(f"\n✅ Success! Rankings saved to: {output_file}")
        return 0

    except Exception as e:
        print(f"\n❌ Error processing rankings: {str(e)}")
        if not args.quiet:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
